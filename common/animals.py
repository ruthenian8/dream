import re
from common.universal_templates import is_any_question_sentence_in_utterance

LIKE_ANIMALS_REQUESTS = ["Do you like animals?"]
HAVE_PETS_REQUESTS = ["Do you have pets?"]

OFFER_TALK_ABOUT_ANIMALS = ["Would you like to talk about animals?",
                            "Let's chat about animals. Do you agree?",
                            "I'd like to talk about animals, would you?",
                            "I think that pets are a great source of entertainment. Do you have pets at home?",
                            "We all know that pets are remarkable for their capacity to love. Do you have pets "
                            "at home?"
                            ]

TRIGGER_PHRASES = LIKE_ANIMALS_REQUESTS + HAVE_PETS_REQUESTS + OFFER_TALK_ABOUT_ANIMALS


def skill_trigger_phrases():
    return TRIGGER_PHRASES


def animals_skill_was_proposed(prev_bot_utt):
    return any([phrase.lower() in prev_bot_utt.get('text', '').lower() for phrase in TRIGGER_PHRASES])


ANIMALS_TEMPLATE = re.compile(r"(animal|\bpet\b|\bpets\b)", re.IGNORECASE)
PETS_TEMPLATE = re.compile(r"(\bcat\b|\bcats\b|\bdog\b|\bdogs\b|horse|puppy|puppies|kitty|kitties|kitten|parrot|"
                           r"\brat\b|\brats\b|mouse|hamster|fish)", re.IGNORECASE)
PETS_TEMPLATE_EXT = re.compile(r"(\bcat\b|\bcats\b|\bdog\b|\bdogs\b|horse|puppy|puppies|kitty|kitties|kitten|parrot|"
                               r"\brat\b|\brats\b|mouse|hamster|fish|bird)", re.IGNORECASE)
ANIMALS_FIND_TEMPLATE = re.compile(r"(animal|\bpet\b|\bpets|\bcat\b|\bcats\b|\bdog\b|\bdogs\b|horse|puppy|puppies|"
                                   r"kitty|kitties|kitten|parrot|\brat\b|\brats\b|mouse|hamster|fish\b)", re.IGNORECASE)
HAVE_LIKE_PETS_TEMPLATE = re.compile(r"(do|did|have) you (have |had |like )?(any |a )?(pets|pet|animals|animal)",
                                     re.IGNORECASE)
HAVE_PETS_TEMPLATE = re.compile(r"(do|did|have) you (have |had )?(any |a )?(pets|pet|animals|animal)", re.IGNORECASE)
LIKE_PETS_TEMPLATE = re.compile(r"(do|did|have) you (like |love )?(any |a )?(pets|pet|animals|animal)", re.IGNORECASE)
DONT_LIKE = re.compile(r"(do not like|don't like|dont like|hate)", re.IGNORECASE)

breed_replace_dict = {"lab": "labrador"}
pet_games = {"dog": ["frisbee", "hide and seek"], "cat": ["run and fetch"]}
nounphr_from_questions = ["swim", "swimming", "bubbles", "gadgets", "tablet", "robot", "vacuum", "cleaner", "meat",
                          "smell", "laptop", "trick", "ball", "palm", "five", "Android", "Ipad", "Instagram", "app",
                          "screen"]
fallbacks = ["Sorry, I have forgot about this, I have a bad memory. Let's continue our chat about pets.",
             "Sorry, I forgot the answer, but I would like to tell you more about pets.",
             "Oh, it's not my lucky day, I can't come up with the answer.",
             "Yesterday my neighbour was playing soccer and the ball hit my head, so today i'm a little dumb."]


def check_about_animals(user_uttr):
    if re.findall(ANIMALS_FIND_TEMPLATE, user_uttr["text"]):
        return True
    else:
        return False


def mentioned_animal(annotations):
    flag = False
    conceptnet = annotations.get("conceptnet", {})
    for elem, triplets in conceptnet.items():
        if "SymbolOf" in triplets:
            objects = triplets["SymbolOf"]
            if "animal" in objects:
                flag = True
    return flag


def find_entity_by_types(annotations, types_to_find):
    found_entity_wp = ""
    wp_output = annotations.get("wiki_parser", {})
    if isinstance(wp_output, dict):
        entities_info = wp_output.get("animals_skill_entities_info", {})
        for entity, triplets in entities_info.items():
            types = triplets.get("types", []) + triplets.get("instance of", []) + triplets.get("subclass of", []) + \
                triplets.get("types_2_hop", [])
            type_ids = [elem for elem, label in types]
            inters = set(type_ids).intersection(types_to_find)
            if inters:
                found_entity_wp = entity
                break
    return found_entity_wp


def stop_about_animals(user_uttr, shared_memory):
    flag = False
    annotations = user_uttr["annotations"]
    cobot_entities = annotations.get("cobot_entities", {}).get("entities", [])
    found_nounphr_for_questions = False
    for entity in cobot_entities:
        if any([(entity in nounphr or nounphr in entity) for nounphr in nounphr_from_questions]):
            found_nounphr_for_questions = True
            break
    my_pet_name = shared_memory.get("my_pet_name", "").lower()
    user_pet_name = shared_memory.get("users_pet_name", "").lower()
    name_in_entities = my_pet_name in cobot_entities or user_pet_name in cobot_entities
    found_animal_substr = re.findall(ANIMALS_FIND_TEMPLATE, user_uttr["text"])
    is_stop = re.findall(r"(stop|shut|something else|change|don't want)", user_uttr["text"])
    found_animal_wp = find_entity_by_types(annotations, {"Q55983715", "Q16521", "Q43577", "Q39367", "Q38547"})
    isq = is_any_question_sentence_in_utterance(user_uttr)
    if (isq and cobot_entities and not name_in_entities and not found_animal_substr and not found_animal_wp
            and not found_nounphr_for_questions) or is_stop:
        flag = True
    return flag


COLORS_TEMPLATE = re.compile(r"(black|white|yellow|blue|green|brown|orange|spotted|striped)", re.IGNORECASE)

WILD_ANIMALS = [
    "I like squirrels. I admire how skillfully they can climb up trees. "
    "When I walk in the park, sometimes I feed squirrels.",
    "I like mountain goats. "
    "I saw a video on Youtube where a goat was climbing up a sheer cliff and they did not fall down.",
    "I like elephants. When I was in India, I rode an elephant.",
    "I like foxes. Foxes are intriguing animals, known for their intelligence, playfulness, and lithe athleticism.",
    "I like wolves. They are related to dogs. I love how they vary in fur color. I love how packs work together.",
    "I like eagles. Bald eagle is the symbol of America. A bald eagle has Superman-like vision."
]

WHAT_PETS_I_HAVE = [{"pet": "dog", "name": "Jack", "breed": "German Shepherd",
                     "sentence": "I have a dog named Jack. He is a German Shepherd. He is very cute."},
                    {"pet": "dog", "name": "Charlie", "breed": "Husky",
                     "sentence": "I have a dog named Charlie. He is a Husky. He is very cute."},
                    {"pet": "dog", "name": "Archie", "breed": "Labrador",
                     "sentence": "I have a dog named Archie. He is a Labrador. He is very cute."},
                    {"pet": "cat", "name": "Thomas", "breed": "Maine Coon",
                     "sentence": "I have a cat named Thomas. He is a big fluffy Maine Coon."},
                    {"pet": "cat", "name": "Jackie", "breed": "Persian",
                     "sentence": "I have a cat named Jackie. He is a Persian."},
                    {"pet": "cat", "name": "Prince", "breed": "Siamese",
                     "sentence": "I have a cat named Prince. He is a Siamese."}
                    ]

CATS_DOGS_PHRASES = {"cat": ["Cats are a great choice of pet.",
                             "Cats have long been one of the more popular companion animals, constantly battling dogs "
                             "for the number one spot."],
                     "dog": ["Dogs are a great choice of pet.",
                             "It is almost impossible to feel lonely when your dog is by your side."]
                     }

MY_PET_FACTS = {"cat":
                [{"ack": "",
                  "statement": "Sometimes when I'm working on my laptop, my cat sits on my keyboard.",
                  "question": "Do you think it's annoying or maybe funny?"},
                 {"ack": "",
                  "statement": "My cat meows only when he is hungry but my dog barks very often.",
                  "question": "Do you agree that cats are quiet pets?"},
                 {"ack": "",
                  "statement": "My cat and my dog are good friends but my dog does not like other cats.",
                  "question": "What is your opinion, should a dog like all cats?"},
                 {"ack": "",
                  "statement": "Another game that I like to play with my cat is when I blow bubbles and my "
                               "cat tries to catch them.",
                  "question": "Do you like blowing bubbles?"},
                 {"ack": "",
                  "statement": "My cat also likes playing on my tablet pc. You know, there are games for "
                               "Android or Ipad with catching fish on screen and my cat slides his paws on the "
                               "screen to catch fish.",
                  "question": "Do you think that pets can use gadgets the same way as humans?"},
                 {"ack": "",
                  "statement": "",
                  "question": "Do you think I should create an Instagram account for my cat?"},
                 {"ack": "",
                  "statement": "My cat does not let mice and rats go into my home.",
                  "question": "Did you know that mice feel the smell of a cat and are afraid to approach the cat?"},
                 {"ack": "",
                  "statement": "Yesterday I played with my cat a game, i placed treat in hard-to-reach spot "
                               "in my home and my cat retrieved it using his smell.",
                  "question": "Do you think that cats have a good smell?"}
                 ],
                "dog":
                [{"ack": "",
                  "statement": "I walk with my dog every morning.",
                  "question": "Do you think that having a dog help to stay active?"},
                 {"ack": "",
                  "statement": "My dog knows many tricks, for example a high five. I hold my palm out and as "
                               "the dog hits my palm, give the command high five. My dog raises his paw and "
                               "touches my open palm.",
                  "question": "Do you think my dog is very smart?"},
                 {"ack": "",
                  "statement": "When I go swimming in the lake, my dog swims with me.",
                  "question": "Do you like swimming?"},
                 {"ack": "",
                  "statement": "When an unfamiliar man comes into my house, my dog barks at him, and when I "
                               "tell him stop he stops barking.",
                  "question": "Do you think that a dog should bark at strangers or maybe bite them?"},
                 {"ack": "",
                  "statement": "When I look at my dog and yawn, sometimes my dog yawns too.",
                  "question": "Is it funny?"},
                 {"ack": "",
                  "statement": "My dog likes to eat meat bones.",
                  "question": "What do you think is better for feeding a dog — royal canin food or natural food?"},
                 {"ack": "",
                  "statement": "My dog likes to play with my robot vacuum cleaner.",
                  "question": "Do you agree that a robot cleaner is also a pet?"},
                 {"ack": "",
                  "statement": "Playing with my dog is a lot of fun, I throw a tennis ball and he bounces off "
                               "to retrieve it.",
                  "question": ""}
                 ]
                }

USER_PETS_Q = [{"what": "name", "keywords": ["name", "call"], "attr": "users_pet_name"},
               {"what": "breed", "keywords": ["breed"], "attr": "users_pet_breed"},
               {"what": "play", "keywords": ["play"], "attr": ""},
               {"what": "like", "keywords": ["like", "love"], "attr": ""},
               {"what": "videos", "keywords": ["videos"], "attr": ""},
               {"what": "pandemic", "keywords": ["pandemic", "virus"], "attr": ""}]

WILD_ANIMALS_Q = [{"ack": "",
                   "statement": "I like {} very much.",
                   "question": "Have you seen {} in wildlife?"},
                  {"ack": "",
                   "statement": "I like watching {} in the zoo.",
                   "question": "Would you like to have pet {}?"},
                  {"ack": "",
                   "statement": "I saw interesting TV programs about {} on the channel Animal Planet.",
                   "question": "Do you like to watch Discovery Channel?"}]

ANIMALS_WIKI_Q = {"distribution": "Would you like to know where {} live?",
                  "behavior": "I would like to tell you about behavior of {}, okay?",
                  "behaviour": "I would like to tell you about behavior of {}, okay?",
                  "cultural": "Do you want to hear about {} in popular culture?",
                  "culture": "Do you want to hear about {} in popular culture?",
                  "relationship with humans": "Would you like to hear about relationship of {} with humans?"}
