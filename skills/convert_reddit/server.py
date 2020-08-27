import logging
import os
import random
import pickle
import time
import json
import difflib
import traceback
import re

import tensorflow_hub as tfhub
import tensorflow as tf
import tensorflow_text
import numpy as np
import spacy
from flask import Flask, request, jsonify
from flasgger import Swagger, swag_from
import sentry_sdk

tensorflow_text.__name__

SENTRY_DSN = os.getenv("SENTRY_DSN")
SEED = 31415
MODEL_PATH = os.getenv("MODEL_PATH")
DATABASE_PATH = os.getenv("DATABASE_PATH")
CONFIDENCE_PATH = os.getenv("CONFIDENCE_PATH")
SOFTMAX_TEMPERATURE = float(os.getenv("SOFTMAX_TEMPERATURE", 0.08))
NUM_SAMPLE = int(os.getenv("NUM_SAMPLE", 3))


sentry_sdk.init(SENTRY_DSN)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(module)s %(lineno)d %(levelname)s : %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
swagger = Swagger(app)

random.seed(SEED)

sess = tf.InteractiveSession(graph=tf.Graph())

module = tfhub.Module(MODEL_PATH)
response_encodings, responses = pickle.load(open(DATABASE_PATH, "rb"))
confidences = np.load(CONFIDENCE_PATH)

nlp = spacy.load("en_core_web_sm")

spaces_pat = re.compile(r"\s+")
special_symb_pat = re.compile(r"[^A-Za-z0-9 ]")


def clear_text(text):
    text = special_symb_pat.sub("", spaces_pat.sub(" ", text.lower().replace("\n", " "))).strip()
    text = text.replace("\u2019", "'")
    return text


banned_responses = json.load(open("./banned_responses.json"))
banned_responses = [clear_text(utter) for utter in banned_responses]
banned_phrases = json.load(open("./banned_phrases.json"))
banned_words = json.load(open("./banned_words.json"))
banned_words_for_questions = json.load(open("./banned_words_for_questions.json"))

text_placeholder = tf.placeholder(dtype=tf.string, shape=[None])
extra_text_placeholder = tf.placeholder(dtype=tf.string, shape=[None])

# The encode_context signature now also takes the extra context.
context_encoding_tensor = module(
    {"context": text_placeholder, "extra_context": extra_text_placeholder}, signature="encode_context"
)

sess.run(tf.tables_initializer())
sess.run(tf.global_variables_initializer())


def encode_context(dialogue_history):
    """Encode the dialogue context to the response ranking vector space.

    Args:
        dialogue_history: a list of strings, the dialogue history, in
            chronological order.
    """

    # The context is the most recent message in the history.
    context = dialogue_history[-1]

    extra_context = list(dialogue_history[:-1])
    extra_context.reverse()
    extra_context_feature = " ".join(extra_context)

    return sess.run(
        context_encoding_tensor,
        feed_dict={text_placeholder: [context], extra_text_placeholder: [extra_context_feature]},
    )[0]


def norm_approximation(confidence):
    return (confidences <= confidence).sum() / len(confidences)


def step_func(x_val, min_x_val, max_x_val, min_y_val, max_y_val):
    if min_x_val <= x_val and x_val <= max_x_val:
        return (x_val - min_x_val) / (max_x_val - min_x_val) * (max_y_val - min_y_val) + min_y_val
    else:
        return 0


def piecewise_approximation(confidence):
    res_confidence = 0.0
    res_confidence = max(res_confidence, step_func(confidence, 0.0, 0.2, 0.0, 0.85))
    res_confidence = max(res_confidence, step_func(confidence, 0.2, 0.4, 0.85, 0.9))
    res_confidence = max(res_confidence, step_func(confidence, 0.4, 1.0, 0.9, 0.95))
    return res_confidence


def approximate_confidence(confidence, approximate_confidence_is_enabled=True, topic_restriction_is_enabled=False):
    print(f"origin_confidence = {confidence}", flush=True)
    confidence = float(confidence)
    confidence = norm_approximation(confidence) if approximate_confidence_is_enabled else confidence
    print(f"norm_confidence = {confidence}", flush=True)
    confidence = piecewise_approximation(confidence) if approximate_confidence_is_enabled else confidence
    confidence = 0.8 * confidence if topic_restriction_is_enabled else confidence
    print(f"approximated_confidence = {confidence}", flush=True)
    return confidence


def get_BOW(sentence):
    filtered_sentence = re.sub("[^A-Za-z0-9]+", " ", sentence).split()
    filtered_sentence = [token for token in filtered_sentence if len(token) > 2]
    return set(filtered_sentence)


unanswered_utters = ["let's talk about", "what else can you do?", "let's talk about books"]
unanswered_utters = [get_BOW(utter) for utter in unanswered_utters]


def is_unanswerable_utters(history):
    last_utter = get_BOW(history[-1])
    for utter in unanswered_utters:
        if len(last_utter & utter) / len(last_utter | utter) > 0.9:
            return True


def softmax(x, t):
    e_x = np.exp((x - np.max(x)) / t)
    return e_x / e_x.sum(axis=0)


def sample_candidates(candidates, choice_num=1, replace=False, softmax_temperature=1):
    choice_num = min(choice_num, len(candidates))
    confidences = [cand[1] for cand in candidates]
    choice_probs = softmax(confidences, softmax_temperature)
    one_dim_candidates = np.array(candidates)
    one_dim_indices = np.arange(len(one_dim_candidates))
    sampled_one_dim_indices = np.random.choice(one_dim_indices, choice_num, replace=replace, p=choice_probs)
    sampled_candidates = one_dim_candidates[sampled_one_dim_indices]
    return sampled_candidates.tolist()


def is_question(sent):
    return re.search("^(do|can|could|will|would|how|who|where|when|what|why)", sent.lower())


def add_question_mark(sent):
    sent = sent.strip()
    if re.findall("[a-z ][.!?]$", sent.lower()):
        sent = sent[:-1] + "?"
    else:
        sent = sent + "?"
    return sent


def format_cand(cand):
    cand = " ".join(
        [(add_question_mark(sent.text) if is_question(sent.text) else sent.text) for sent in nlp(cand).sents]
    )
    return cand


restricted_topics = set(
    [
        "news",
        "movies",
        "books",
        "weather",
        "games",
        # "music",
        # "entertainments",
        # "fashions",
        # "science_technology",
        # "sports",
        # "animals",
    ]
)


def is_restricted_topic(agent_topics):
    return bool(set([k for k, v in agent_topics.items() if v]) & restricted_topics)


def inference(utterances_histories, approximate_confidence_is_enabled=True, topic_restriction_is_enabled=False):
    context_encoding = encode_context(utterances_histories)
    scores = context_encoding.dot(response_encodings.T)
    indices = np.argsort(scores)[::-1][:10]
    filtered_indices = []
    for ind in indices:
        cand = responses[ind]
        if not [
            None
            for f_utter in banned_responses
            if difflib.SequenceMatcher(None, f_utter.split(), clear_text(cand).split()).ratio() > 0.9
        ]:
            filtered_indices.append(ind)

    if is_unanswerable_utters(utterances_histories):
        return "", 0.0

    clear_utterances_histories = [clear_text(utt).split() for utt in utterances_histories[::-1][1::2][::-1]]

    for ind in reversed(filtered_indices):
        cand = clear_text(responses[ind]).split()
        raw_cand = responses[ind].lower()
        # hello ban
        hello_flag = any([j in cand[:3] for j in ["hi", "hello"]])
        # banned_words ban
        banned_words_flag = any([j in cand for j in banned_words])
        banned_words_for_questions_flag = any([(j in cand and "?" in raw_cand) for j in banned_words_for_questions])

        # banned_phrases ban
        banned_phrases_flag = any([j in raw_cand for j in banned_phrases])

        # ban long words
        long_words_flag = any([len(j) > 30 for j in cand])

        if hello_flag or banned_words_flag or banned_words_for_questions_flag or banned_phrases_flag or long_words_flag:
            filtered_indices.remove(ind)
            continue
        for utterance in clear_utterances_histories:
            if difflib.SequenceMatcher(None, utterance, cand).ratio() > 0.6:
                filtered_indices.remove(ind)
                break

    if len(filtered_indices) > 0:
        candidates = [
            (
                clear_text(responses[ind]),
                approximate_confidence(scores[ind], approximate_confidence_is_enabled, topic_restriction_is_enabled),
            )
            for ind in filtered_indices
        ]
        try:
            selected_candidates = sample_candidates(
                candidates, choice_num=NUM_SAMPLE, softmax_temperature=SOFTMAX_TEMPERATURE
            )
            answers = [format_cand(cand[0]) for cand in selected_candidates]
            confidences = [float(cand[1]) for cand in selected_candidates]
            return answers, confidences
        except Exception:
            logger.error(traceback.format_exc())
            candidate = candidates[0]
            return candidate
    else:
        return "", 0.0


@app.route("/convert_reddit", methods=["POST"])
@swag_from("chitchat_endpoint.yml")
def convert_chitchat_model():
    st_time = time.time()
    utterances_histories = request.json["utterances_histories"]
    topic_batch = request.json["agent_topics"]
    approximate_confidence_is_enabled = request.json.get("approximate_confidence_is_enabled", True)
    response = [
        inference(hist, approximate_confidence_is_enabled, is_restricted_topic(topics))
        for hist, topics in zip(utterances_histories, topic_batch)
    ]
    total_time = time.time() - st_time
    logger.warning(f"convert_reddit answ: {response}")
    logger.warning(f"convert_reddit exec time: {total_time:.3f}s")
    return jsonify(response)
