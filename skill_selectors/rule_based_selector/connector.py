import asyncio
import logging
import re
from itertools import chain
from os import getenv
from typing import Dict, Callable

import sentry_sdk

from common.movies import movie_skill_was_proposed
from common.animals import animals_skill_was_proposed
from common.food import food_skill_was_proposed
from common.books import book_skill_was_proposed, about_book, QUESTIONS_ABOUT_BOOKS
from common.constants import CAN_NOT_CONTINUE, CAN_CONTINUE_SCENARIO, MUST_CONTINUE, CAN_CONTINUE_SCENARIO_DONE
from common.emotion import emotion_from_feel_answer, is_joke_requested, is_sad
from common.greeting import HOW_ARE_YOU_RESPONSES, GREETING_QUESTIONS
from common.news import is_breaking_news_requested
from common.universal_templates import if_lets_chat_about_topic, if_choose_topic, switch_topic_uttr
from common.utils import high_priority_intents, low_priority_intents, \
    get_topics, get_intents, get_emotions
from common.weather import is_weather_requested
from common.coronavirus import check_about_death, about_virus, quarantine_end, is_staying_home_requested
import common.travel as common_travel
import common.music as common_music
import common.sport as common_sport
from common.animals import check_about_pets

sentry_sdk.init(getenv('SENTRY_DSN'))
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)


class RuleBasedSkillSelectorConnector:
    sensitive_topics = {"Politics", "Religion", "Sex_Profanity", "Inappropriate_Topic"}
    # `General_ChatIntent` sensitive in case when `?` in reply
    sensitive_dialogacts = {"Opinion_RequestIntent", "General_ChatIntent"}
    movie_cobot_dialogacts = {
        "Entertainment_Movies",
        "Sports",
        "Entertainment_Music",
        "Entertainment_General"
    }
    movie_cobot_topics = {
        "Movies_TV",
        "Celebrities",
        "Art_Event",
        "Entertainment",
        "Fashion",
        "Games",
        "Music",
        "Sports",
    }
    entertainment_cobot_dialogacts = {
        "Entertainment_Movies",
        "Entertainment_Music",
        "Entertainment_General",
        "Entertainment_Books",
    }
    entertainment_cobot_topics = {
        "Art_Event",
        "Celebrities",
        "Entertainment",
        "Games",
    }
    fashion_cobot_dialogacts = set()
    fashion_cobot_topics = {
        "Fashion",
    }
    science_cobot_dialogacts = {
        "Science_and_Technology",
        "Entertainment_Books",
    }
    science_cobot_topics = {
        "Literature",
        "Math",
        "SciTech",
    }
    science_cobot_dialogacts = {
        "Science_and_Technology",
        "Entertainment_Books",
    }
    science_cobot_topics = {
        "Literature",
        "Math",
        "SciTech",
    }
    # politic_cobot_dialogacts = {
    #     "Politics",
    # }
    # politic_cobot_topics = {
    #     "Politics",
    # }
    sport_cobot_dialogacts = {
        "Sports",
    }
    sport_cobot_topics = {
        "Sports",
    }
    animals_cobot_topics = {
        "Pets_Animals",
    }
    food_cobot_topics = {
        "Food_Drink",
    }
    books_cobot_dialogacts = {"Entertainment_General", "Entertainment_Books"}
    books_cobot_topics = {"Entertainment", "Literature"}
    news_cobot_topics = {"News"}
    about_movie_words = re.compile(r"(movie|film|picture|series|tv[ -]?show|reality[ -]?show|netflix|\btv\b|"
                                   r"comedy|comedies|thriller|animation|anime|talk[ -]?show|cartoon|drama|"
                                   r"fantasy)")

    async def send(self, payload: Dict, callback: Callable):
        try:
            dialog = payload['payload']['states_batch'][0]

            skills_for_uttr = []
            user_uttr_text = dialog["human_utterances"][-1]["text"].lower()
            user_uttr_annotations = dialog["human_utterances"][-1]["annotations"]
            lets_chat_about_particular_topic = if_lets_chat_about_topic(user_uttr_text)

            intent_catcher_intents = get_intents(dialog['human_utterances'][-1], probs=False, which="intent_catcher")
            high_priority_intent_detected = any([k for k in intent_catcher_intents
                                                 if k in high_priority_intents["intent_responder"]])
            low_priority_intent_detected = any([k for k in intent_catcher_intents
                                                if k in low_priority_intents])

            ner_detected = len(list(chain.from_iterable(user_uttr_annotations.get("ner", [])))) > 0
            logger.info(f"Detected Entities: {ner_detected}")

            cobot_topics = set(get_topics(dialog["human_utterances"][-1], which="cobot_topics"))
            sensitive_topics_detected = any([t in self.sensitive_topics for t in cobot_topics])

            cobot_dialogacts = get_intents(dialog['human_utterances'][-1], which="cobot_dialogact_intents")
            cobot_dialogact_topics = set(get_topics(dialog['human_utterances'][-1], which="cobot_dialogact_topics"))
            # factoid
            factoid_classification = user_uttr_annotations.get('factoid_classification', {}).get('factoid', 0.)
            # using factoid
            factoid_prob_threshold = 0.9  # to check if factoid probability has at least this prob
            sensitive_dialogacts_detected = any(
                [(t in self.sensitive_dialogacts and "?" in user_uttr_text) for t in cobot_dialogacts]
            ) or "opinion_request" in intent_catcher_intents
            blist_topics_detected = user_uttr_annotations.get("blacklisted_words", {}).get("restricted_topics", 0)

            about_movies = (self.movie_cobot_dialogacts & cobot_dialogact_topics)
            about_music = ("Entertainment_Music" in cobot_dialogact_topics) | ("Music" in cobot_topics)
            about_games = ("Games" in cobot_topics and "Entertainment_General" in cobot_dialogact_topics)
            about_books = about_book(dialog["human_utterances"][-1])

            #  topicalchat_tfidf_retrieval
            about_entertainments = (self.entertainment_cobot_dialogacts & cobot_dialogact_topics) | \
                                   (self.entertainment_cobot_topics & cobot_topics)
            about_fashions = (self.fashion_cobot_dialogacts & cobot_dialogact_topics) | \
                             (self.fashion_cobot_topics & cobot_topics)
            # about_politics = (politic_cobot_dialogacts & cobot_dialogact_topics) | (sport_cobot_topics & cobot_topics)
            about_science_technology = (self.science_cobot_dialogacts & cobot_dialogact_topics) | \
                                       (self.science_cobot_topics & cobot_topics)
            about_sports = (self.sport_cobot_dialogacts & cobot_dialogact_topics) | \
                           (self.sport_cobot_topics & cobot_topics)

            prev_user_uttr_hyp = []
            prev_bot_uttr = {}

            if len(dialog["human_utterances"]) > 1:
                prev_user_uttr_hyp = dialog["human_utterances"][-2]["hypotheses"]

            if len(dialog['bot_utterances']) > 0:
                prev_bot_uttr = dialog["bot_utterances"][-1]

            prev_active_skill = prev_bot_uttr.get("active_skill", "")
            greeting_what_to_talk_question = any([question.lower() in prev_bot_uttr.get("text", "").lower()
                                                  for question in GREETING_QUESTIONS["what_to_talk_about"]])

            weather_city_slot_requested = any(
                [
                    hyp.get("weather_forecast_interaction_city_slot_requested", False)
                    for hyp in prev_user_uttr_hyp
                    if hyp["skill_name"] == "weather_skill"
                ]
            )

            last_user_sent_text = dialog["human_utterances"][-1].get(
                "annotations", {}).get("sentseg", {}).get("segments", [""])[-1].lower()
            switch_choose_topic = switch_topic_uttr(
                dialog["human_utterances"][-1]) or if_choose_topic(
                last_user_sent_text, prev_uttr=prev_bot_uttr.get("text", "").lower())

            about_weather = "weather_forecast_intent" in intent_catcher_intents or (
                prev_bot_uttr.get("active_skill", "") == "weather_skill" and weather_city_slot_requested
            ) or (lets_chat_about_particular_topic and "weather" in user_uttr_text)
            about_weather = about_weather or is_weather_requested(prev_bot_uttr, dialog['human_utterances'][-1])
            news_re_expr = re.compile(r"(news|(what is|what ?'s)( the)? new|something new)")
            about_news = (self.news_cobot_topics & cobot_topics) or re.search(news_re_expr, user_uttr_text)
            about_news = about_news or is_breaking_news_requested(prev_bot_uttr, dialog['human_utterances'][-1])
            virus_prev = False
            for i in [3, 5]:
                if len(dialog['utterances']) >= i:
                    virus_prev = virus_prev or any([function(dialog['utterances'][-i]['text'])
                                                    for function in [about_virus, quarantine_end]])
            enable_coronavirus_death = check_about_death(user_uttr_text)
            enable_grounding_skill = "what_are_you_talking_about" in intent_catcher_intents
            enable_coronavirus = any([function(user_uttr_text)
                                      for function in [about_virus, quarantine_end]])
            enable_coronavirus = enable_coronavirus or (enable_coronavirus_death and virus_prev)
            enable_coronavirus = enable_coronavirus or is_staying_home_requested(
                prev_bot_uttr, dialog['human_utterances'][-1])
            about_movies = (about_movies or movie_skill_was_proposed(prev_bot_uttr) or re.search(
                self.about_movie_words, prev_bot_uttr.get("text", "").lower()))
            about_books = about_books or book_skill_was_proposed(prev_bot_uttr)
            about_food = (self.food_cobot_topics & cobot_topics) or food_skill_was_proposed(prev_bot_uttr)
            about_animals = self.animals_cobot_topics & cobot_topics or animals_skill_was_proposed(prev_bot_uttr)
            about_pets = check_about_pets(dialog["human_utterances"][-1]["text"])
            emotions = get_emotions({'annotations': user_uttr_annotations}, probs=True)
            # check that logging of if empty is in get_emotion and delete string than

            # print(f"Skill Selector: did we select game_cooperative_skill? {about_games}", flush=True)

            if "/new_persona" in user_uttr_text:
                # process /new_persona command
                skills_for_uttr.append("personality_catcher")  # TODO: rm crutch of personality_catcher
            elif user_uttr_text == "/get_dialog_id":
                skills_for_uttr.append("dummy_skill")
            elif high_priority_intent_detected:
                # process intent with corresponding IntentResponder
                skills_for_uttr.append("intent_responder")
            elif blist_topics_detected or (sensitive_topics_detected and sensitive_dialogacts_detected):
                # process user utterance with sensitive content, "safe mode"
                skills_for_uttr.append("program_y_dangerous")
                skills_for_uttr.append("cobotqa")
                # skills_for_uttr.append("cobotqa")
                skills_for_uttr.append("meta_script_skill")
                skills_for_uttr.append("personal_info_skill")
                if about_news or lets_chat_about_particular_topic:
                    skills_for_uttr.append("news_api_skill")
                if enable_coronavirus or prev_active_skill == 'coronavirus_skill':
                    skills_for_uttr.append("coronavirus_skill")
                skills_for_uttr.append("factoid_qa")
            else:
                if low_priority_intent_detected:
                    skills_for_uttr.append("intent_responder")
                if enable_grounding_skill:
                    skills_for_uttr.append("grounding_skill")
                # process regular utterances
                skills_for_uttr.append("program_y")
                skills_for_uttr.append("cobotqa")
                skills_for_uttr.append("christmas_new_year_skill")
                skills_for_uttr.append("superbowl_skill")
                # skills_for_uttr.append("oscar_skill")
                skills_for_uttr.append("valentines_day_skill")
                skills_for_uttr.append("personal_info_skill")
                skills_for_uttr.append("meta_script_skill")
                if len(dialog["utterances"]) < 20:
                    # greeting skill inside itself do not turn on later than 10th turn of the conversation
                    # skills_for_uttr.append("greeting_skill")
                    skills_for_uttr.append("dff_friendship_skill")
                if switch_choose_topic:
                    skills_for_uttr.append("knowledge_grounding_skill")
                    pass

                if len(dialog["utterances"]) > 8 or (
                    (
                        prev_bot_uttr.get("active_skill", "") in ["greeting_skill", "dff_friendship_skill"]
                    ) and greeting_what_to_talk_question
                ):
                    skills_for_uttr.append("knowledge_grounding_skill")
                    # skills_for_uttr.append("wikidata_dial_skill")

                # hiding factoid by default, adding check for factoid classification instead
                # skills_for_uttr.append("factoid_qa")
                if (factoid_classification > factoid_prob_threshold):
                    skills_for_uttr.append("factoid_qa")

                # if ner_detected:
                #     skills_for_uttr.append("reddit_ner_skill")

                if len(dialog["human_utterances"]) >= 5:
                    # can answer on 4-th user response
                    skills_for_uttr.append("convert_reddit")
                    skills_for_uttr.append("comet_dialog_skill")
                if len(dialog["utterances"]) > 14:
                    skills_for_uttr.append("alice")
                    skills_for_uttr.append("program_y_wide")
                # if len(dialog["utterances"]) > 7:
                # Disable topicalchat_convert_retrieval v8.7.0
                # skills_for_uttr.append("topicalchat_convert_retrieval")

                if ('dummy_skill' in prev_bot_uttr.get("active_skill", "") and len(dialog["utterances"]) > 4):
                    skills_for_uttr.append("dummy_skill_dialog")

                # thematic skills
                if about_movies or prev_active_skill == 'movie_skill':
                    skills_for_uttr.append("movie_skill")
                    skills_for_uttr.append("movie_tfidf_retrieval")
                if enable_coronavirus or prev_active_skill == 'coronavirus_skill':
                    skills_for_uttr.append("coronavirus_skill")
                if about_music and len(dialog["utterances"]) > 2:
                    skills_for_uttr.append("music_tfidf_retrieval")
                if about_animals or about_pets or prev_active_skill == 'dff_animals_skill':
                    skills_for_uttr.append("dff_animals_skill")
                if about_food or prev_active_skill == 'dff_food_skill':
                    skills_for_uttr.append("dff_food_skill")

                linked_to_music = False
                if len(dialog["bot_utterances"]) > 0:
                    linked_to_music = any([phrase.lower() in dialog["bot_utterances"][-1]["text"].lower()
                                           for phrase in list(common_music.skill_trigger_phrases())])

                if about_music or prev_active_skill == 'dff_music_skill' or linked_to_music:
                    skills_for_uttr.append("dff_music_skill")

                linked_to_book = False
                if len(dialog["bot_utterances"]) > 0:
                    linked_to_book = any([phrase in dialog["bot_utterances"][-1]["text"]
                                          for phrase in QUESTIONS_ABOUT_BOOKS])

                if about_books or prev_active_skill == 'book_skill' or linked_to_book:
                    skills_for_uttr.append("book_skill")
                    skills_for_uttr.append("book_tfidf_retrieval")

                if about_games:
                    skills_for_uttr.append("game_cooperative_skill")

                if about_weather:
                    skills_for_uttr.append("weather_skill")

                if about_entertainments and len(dialog["utterances"]) > 2:
                    skills_for_uttr.append("entertainment_tfidf_retrieval")

                if about_fashions and len(dialog["utterances"]) > 2:
                    skills_for_uttr.append("fashion_tfidf_retrieval")

                # if about_politics and len(dialog["utterances"]) > 2:
                #     skills_for_uttr.append("politics_tfidf_retrieval")

                if about_science_technology and len(dialog["utterances"]) > 2:
                    skills_for_uttr.append("science_technology_tfidf_retrieval")

                if about_sports and len(dialog["utterances"]) > 2:
                    skills_for_uttr.append("sport_tfidf_retrieval")

                if about_animals and len(dialog["utterances"]) > 2:
                    skills_for_uttr.append("animals_tfidf_retrieval")

                if about_news or lets_chat_about_particular_topic:
                    skills_for_uttr.append("news_api_skill")

                # joke requested
                if is_joke_requested(dialog["human_utterances"][-1]['text']):
                    # if there is no "bot" key in our dictionary, we manually create it
                    if "bot" not in dialog:
                        dialog['bot'] = {}
                    # if there is no "attributes" key in our dictionary, we manually create it
                    if "attributes" not in dialog['bot']:
                        dialog['bot']['attributes'] = {}
                    # if there is no "emotion_skill_attributes" in our dictionary, we manually create it
                    if "emotion_skill_attributes" not in dialog['bot']['attributes']:
                        dialog['bot']['attributes']['emotion_skill_attributes'] = {}

                    emotion_skill_attributes = dialog['bot']['attributes']['emotion_skill_attributes']
                    emotion_skill_attributes['state'] = "joke_requested"
                    dialog['bot']['attributes']['emotion_skill_attributes'] = emotion_skill_attributes
                    skills_for_uttr.append("joke")

                emo_prob_threshold = 0.9  # to check if any emotion has at least this prob
                found_emotion, found_prob = 'neutral', 1
                for emotion, prob in emotions.items():
                    if prob == max(emotions.values()):
                        found_emotion, found_prob = emotion, prob
                emo_found_emotion = found_emotion != 'neutral' and found_prob > emo_prob_threshold
                good_emotion_prob = max([emotions.get('joy', 0), emotions.get('love', 0)])
                bad_emotion_prob = max([emotions.get('anger', 0), emotions.get('fear', 0), emotions.get('sadness', 0)])
                not_strange_emotion_prob = not (good_emotion_prob > 0.5 and bad_emotion_prob > 0.5)
                how_are_you = any([how_are_you_response.lower() in prev_bot_uttr.get("text", "").lower()
                                   for how_are_you_response in HOW_ARE_YOU_RESPONSES])
                joke_request_detected = is_joke_requested(dialog['human_utterances'][-1].get("text", ""))
                sadness_detected_by_regexp = is_sad(dialog['human_utterances'][-1].get("text", ""))
                detected_from_feel_answer = emotion_from_feel_answer(prev_bot_uttr.get("text", ""),
                                                                     dialog['human_utterances'][-1].get("text", ""))
                should_run_emotion = any([emo_found_emotion,
                                          joke_request_detected,
                                          sadness_detected_by_regexp,
                                          detected_from_feel_answer,
                                          how_are_you]) and not_strange_emotion_prob
                if should_run_emotion:
                    skills_for_uttr.append('emotion_skill')

                for hyp in prev_user_uttr_hyp:
                    # here we just forcibly add skills which return `can_continue` and it's not `no`
                    if hyp.get("can_continue", CAN_NOT_CONTINUE) in {CAN_CONTINUE_SCENARIO, MUST_CONTINUE,
                                                                     CAN_CONTINUE_SCENARIO_DONE}:
                        skills_for_uttr.append(hyp["skill_name"])

                if len(dialog["utterances"]) > 1:
                    # Use only misheard asr skill if asr is not confident and skip it for greeting
                    if user_uttr_annotations.get("asr", {}).get("asr_confidence", "high") == "very_low":
                        skills_for_uttr = ["misheard_asr"]

                named_entities = []
                for ent in user_uttr_annotations.get("ner", []):
                    if not ent:
                        continue
                    ent = ent[0]
                    named_entities.append(ent)

                about_travel = "Travel_Geo" in cobot_topics or any([ent["type"] == "LOC" for ent in named_entities])
                user_about_travel = re.search(common_travel.TRAVELLING_TEMPLATE, dialog["human_utterances"][-1]["text"])
                linked_to_travel = False
                if len(dialog["bot_utterances"]) > 0:
                    linked_to_travel = any([phrase.lower() in dialog["bot_utterances"][-1]["text"].lower()
                                            for phrase in list(common_travel.skill_trigger_phrases())])

                if about_travel or user_about_travel or linked_to_travel or prev_active_skill == "dff_travel_skill":
                    skills_for_uttr.append("dff_travel_skill")

                if about_travel or user_about_travel or linked_to_travel or prev_active_skill == "dff_travel_skill":
                    skills_for_uttr.append("dff_travel_skill")

                # add sport skill
                about_sport = "Sports" in cobot_topics
                user_about_kind_of_sport = re.search(
                    common_sport.KIND_OF_SPORTS_TEMPLATE, dialog["human_utterances"][-1]["text"]
                )
                user_about_kind_of_comp = re.search(
                    common_sport.KIND_OF_COMPETITION_TEMPLATE, dialog["human_utterances"][-1]["text"]
                )
                user_about_athlete = re.search(common_sport.ATHLETE_TEMPLETE, dialog["human_utterances"][-1]["text"])
                user_about_comp = re.search(common_sport.COMPETITION_TEMPLATE, dialog["human_utterances"][-1]["text"])
                linked_to_sport = False
                if len(dialog["bot_utterances"]) > 0:
                    linked_to_sport = any(
                        [
                            phrase.lower() in dialog["bot_utterances"][-1]["text"].lower()
                            for phrase in list(common_sport.skill_trigger_phrases())
                        ]
                    )
                flag = (
                    bool(about_sport)
                    or bool(user_about_kind_of_sport)
                    or bool(user_about_kind_of_comp)
                    or bool(user_about_athlete)
                    or bool(user_about_comp)
                    or bool(linked_to_sport)
                    or prev_active_skill == "dff_sport_skill"
                )
                if flag:
                    skills_for_uttr.append("dff_sport_skill")

            # always add dummy_skill
            skills_for_uttr.append("dummy_skill")
            #  no convert when about coronavirus
            if 'coronavirus_skill' in skills_for_uttr and 'convert_reddit' in skills_for_uttr:
                skills_for_uttr.remove('convert_reddit')
            if 'coronavirus_skill' in skills_for_uttr and 'comet_dialog_skill' in skills_for_uttr:
                skills_for_uttr.remove('comet_dialog_skill')

            # (yura): do we really want to always turn small_talk_skill?
            if len(dialog["utterances"]) > 14 or lets_chat_about_particular_topic:
                skills_for_uttr.append("small_talk_skill")

            if "/alexa_" in user_uttr_text:
                skills_for_uttr = ["alexa_handler"]
            logger.info(f"Selected skills: {skills_for_uttr}")
            asyncio.create_task(callback(
                task_id=payload['task_id'],
                response=list(set(skills_for_uttr))
            ))
        except Exception as e:
            logger.exception(e)
            sentry_sdk.capture_exception(e)
            asyncio.create_task(callback(
                task_id=payload['task_id'],
                response=["program_y", "dummy_skill", "cobotqa"]
            ))
