# Author: Tibor Tonn, Matthias Kraus, Nicolas Wagner


# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/core/actions/#custom-actions/


# import time
from typing import List, Dict, Text, Any, Union

from rasa_sdk import Tracker
# from rasa_sdk.executor import CollectingDispatcher
# ___________________________________________________________________________
from rasa_sdk import Action
from rasa_sdk.events import SlotSet, Form, FollowupAction, ReminderScheduled, AllSlotsReset
from rasa_sdk.forms import FormAction
from random import randrange
import datetime
import time
import json
import requests
import paho.mqtt.client as mqtt

# ___________________________
import room_shelf
import german_gender_wiki


# globale Variablen. Die werden benötigt um infromationen von MQTT zubekommen und weier zu geben
output = None  # hier muss man kein global schreiben nur wenn man in der Funktion eine globale Variable verwendet
globalort = None

missingInfo = None
globalAlternative = None # globaler Alternativenslot, da External Intents keine Slots füllen
globalTaskID = None
globalDbLocation = None

globalLastAction = None

anomtype = None  # Variable, um den Typ der Anomalie später für Fallunterscheidungen zu speichern

answobjects = None

# Die answer_flag bestimmt ob man auf eine Antwort von dem Roboter wartet.
# In der späteren Benutzung wird man immer auf eine Antwort des Roboters warten
# beim entwickeln ist es aber imme ein bischen nervig andauernd mit einem anderen Gerät MQTT-Nachrichten zu verschicken
answer_flag = 1  # 0=wartet auf keine Antwort #1=wartet auf Antwort

client = mqtt.Client("ds")

host_name = "134.60.153.113"

client.connect(host_name, 1883, 60)

# Offizielle topicTask
topicTask="/dialogue/task"
topicStatus="/robots/status"
topicRobotTask="/robots/task"
topicDialStatus="/dialogue/status"

client.loop_start()

client.subscribe(topicStatus)
client.subscribe(topicRobotTask)

def makeSuccessJSON(dson):

    tempPrio = 3
    if "priority" in dson:
        tempPrio = dson["priority"]

    #if dson["type"] == TODO TYPEFESTLEGEN
    mqttjson = {
        "target_id": dson["source_id"],
        "source_id": "dm",
        "timestamp": int(time.time()),
        "task_id": dson["task_id"],
        "priority": tempPrio,
        "type": "success",
        "parameter": {"success": True}
    }
    return json.dumps(mqttjson) # Python object in Json convertieren

# Funktion für Nachrichten von MQTT
def on_message(client, userdata, message):

    global globalmessage
    global output  # hier muss ich global schreiben da ich output einen anderen Wert zuweise
    global topicName
    # TH: ---globale Variablen, die in den Actions verwendet werden
    global missingInfo
    global globalAlternative  # Im Moment muss man hier für die Alternative, die einem vom Roboter angeboten wird, eine
    # globale Variable anlegen, weil durch External Trigger (warum auch immer) keine Slots mit Entities gefüllt werden.
    global globalTaskID
    global anomtype
    global globalLastAction
    data = ""

    output = str(message.payload.decode("utf-8"))
    topicName = message.topic
    try:
        dson = json.loads(output)  # convert message to python dic (if message format is JSON, though)
        print("message received: ", dson["type"], "on Topic: ", message.topic)  # TH: print message from Kurt
    except IOError as exc:
        dson = ""
        raise RuntimeError("JSON in wrong format, could not decode") from exc

    #Fallunterscheidung der Nachrichtentypen
    if "type" in dson:

        # Anomalie wie Müll oder Zeitung entdeckt
        if dson["type"] == "anomaly_detected":
            print("anomaly detected")
            
            if "parameter" in dson and "location" in dson["parameter"] and "objects" in dson["parameter"]:
                anomtype = dson["parameter"]["objects"][0]
                print("Typ der Anomalie: " + anomtype)
                data = '{"name": "EXTERNAL_anomaly_detected", "entities": {"anomaly":"'+anomtype+'", "furniture":"'+dson["parameter"]["location"]+'", "alternative_place1":"Regal","alternative_place2":"Regal"}}'
                globalLastAction = "anomaly_detected"
                topublish = makeSuccessJSON(dson)  # Python object in Json convertieren
                client.publish(topicDialStatus, topublish)
            else:
                print("ERROR, wrong format for incoming task: anomaly_detected")

       
        elif dson["type"] == "alternatives":
            print("offering alternatives")
            
            if "parameter" in dson and "alternatives" in dson["parameter"]:
                print("alternative found: " + dson["parameter"]["alternatives"][0])
                data = '{"name": "EXTERNAL_alternative", "entities": {"alternatives": "' + dson["parameter"]["alternatives"][0] + '"}}'
                globalAlternative = dson["parameter"]["alternatives"][0]  # Alternative global setzen
                globalTaskID = dson["task_id"]
                # data = '{"name": "EXTERNAL_alternative", "entities": {"alternative": "Fanta"}}'
                globalLastAction = "alternatives"
                topublish = makeSuccessJSON(dson)  # Python object in Json convertieren
                client.publish(topicDialStatus, topublish)

            else:
                print("ERROR, wrong format for incoming task: offering_alternatives")
    
        elif dson["type"] == "confirm":
            print("Confirm message received")

        elif dson["type"]  == "success":
            print("Success message received")
            success = dson["parameter"]["success"]
            print("success: "+ success)

            data = '{"name": "EXTERNAL_success", "entities": {"success": "' + success + '"}}'


        elif dson["type"] == "progress":
            print("Progress message received")
            #todo try catch
            performedAction = dson["parameter"]["performed_actions"][0]
            print("performed action: " , performedAction)

            if performedAction["action"] == "handover_start":
                print("handover started")
                print("target: " + performedAction["target"])
                data = '{"name": "EXTERNAL_handover_start", "entities": {"handover_start": "'+ performedAction["target"]+'"}}'
                globalLastAction = "handover_start"
                topublish = makeSuccessJSON(dson)  # Python object in Json convertieren
                client.publish(topicDialStatus, topublish)
                    
            elif performedAction["action"] == "handover_completed":
                print("handover completed")
                print("target: " + performedAction["target"])
                data = '{"name": "EXTERNAL_handover_completed", "entities": {"handover_completed": "' + performedAction["target"] + '"}}'
                globalLastAction = "handover_completed"
                topublish = makeSuccessJSON(dson)  # Python object in Json convertieren
                client.publish(topicDialStatus, topublish)
                    
            elif performedAction["action"] == "person_detected":
                print("Person Detected")
                print("target: " + performedAction["target"])
                data = '{"name": "EXTERNAL_person_detected", "entities": {"person_detected": "' + performedAction["target"] + '"}}'
                globalLastAction = "person_detected"
                topublish = makeSuccessJSON(dson)  # Python object in Json convertieren
                client.publish(topicDialStatus, topublish)

        else:
            print("nothing to do")

        # trigger external intent
        headers = {'Content-Type': 'application/json', }
        params = (('output_channel', 'latest'),)
        if data:
            requests.post('http://localhost:5005/conversations/user/trigger_intent', headers=headers,
                      params=params, data=data)
            print("\n")
            print("POST COMMITTED: " + data)
            print("\n")
        else:
            print("no important message, nothing posted to rasa server")
    else:
        print("no type, message cannot be intepreted")

#  Eingehende Nachrichten werden verarbeitet

client.on_message = on_message

class ActionSendBring(Action):
    def name(self):

        return "action_bring"

    def run(self, dispatcher, tracker, domain):
        print("action_bring wird gestartet")
        global globalTaskID
        globalLastAction = "bring"
        if tracker.get_slot('gegenstand') is not None:
            # wenn möglich einfach in utf-8 umwandeln
            gegenstand = tracker.get_slot('gegenstand')
            gegenstand = gegenstand.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "Oe").replace("ü", "ue").replace("Ü", "Ue")
            gegenstand = gegenstand.lower()
        else:
            gegenstand = "Gegenstand nicht definiert"

        place = tracker.get_slot('place')
        # globalort = tracker.get_slot('ort')#soll das getrackte wort bekommen
        if place is not None:
            place = place.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü", "ue")\
                .replace("Ü", "Ue")
            place = place.lower()
        else:
            place = tracker.get_slot('furniture')
            if place is None:
                place = ""
            place = place.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü","ue")\
                .replace("Ü", "Ue")
            place = place.lower()

        task_id = "TaskID_"

        tempTimestamp = int(time.time())
        if globalTaskID is not None:
            tempTaskID = globalTaskID
            globalTaskID = None
        else:
            tempTaskID = "task" + str(tempTimestamp)

        missing_info = tracker.get_slot("missing_info")

        # Json-file als object erstellen
        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": tempTimestamp,
            "task_id": tempTaskID,
            "priority": 3,
            "type": "bring",
            "parameter": {
                "object": gegenstand,
                "from": missing_info,
                "to": "user",
            }
        }
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # in MQTT verschickt


        # Anzeigen was raus geschickt wurde
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        gegenstand = str(tracker.get_slot('gegenstand')).title()
        gender = german_gender_wiki.search(gegenstand)

        if (gender == "N" or gender == "M"):
            artikel = "dein "
            # SlotSet("artikel", "dein")
        elif (gender == "F"):
            artikel = "deine "
            # SlotSet("artikel","deine")
        else:
            artikel = "deine "  # da es Mehrzahl sein könnte (Chips)

        # antwort_str = "Ich hole dir " + artikel + gegenstand

        # TH: hier soll soll erst mal nur bestätigt werden, für den fall, dass der roboter den gegenstand nicht findet
        antwort_str = "Alles klar, verstanden."
        dispatcher.utter_message(antwort_str)

       # if tracker.get_slot("proactive_level") is None:
         #   optionInt = 1
       # else:
         #  optionInt = tracker.get_slot("proactive_level")

        #optionInt += 1
        #if optionInt > 4:
            #optionInt == 4

        return [SlotSet("gegenstand", gegenstand)]

class ActionOfferClean(Action):
    def name(self):
        return "action_offer_clean"

    def run(self, dispatcher, tracker, domain):

        print("action_offer_clean wird gestartet")

        globalLastAction = "offer_clean"

        if tracker.get_slot("proactive_level") is None:
            optionInt = randrange(1,3)
        else:
            optionInt = tracker.get_slot("proactive_level")

        if optionInt == 4:  # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("clean option 1 chosen")

            dispatcher.utter_message("Ich habe bemerkt, dass du vom Einkaufen zurück bist. Ich werde ihn jetzt für dich aufräumen")


            return [FollowupAction("action_clean"), SlotSet("proactive_level",3)]

        elif optionInt == 3:  # proaktiv, variante 2: ja/nein-antwort

            print("clean option 2 chosen")


            dispatcher.utter_message("Ich habe bemerkt, dass du vom Einkaufen zurück bist. Soll ich ihn für dich aufräumen?")

        elif optionInt == 2:  # proaktiv, variante 1: option zum aufräumbefehl

            print("\n")
            print("clean option 3 has been chosen")
            print("\n")


            dispatcher.utter_message("Ich habe bemerkt, dass du vom Einkaufen zurück bist.")


        elif optionInt == 1:  # reaktiv: nutzer:in gibt befehl, Roboter äußert sich nicht

            print("\n")
            print("clean option 4 chosen")
            print("\n")

        return

class ActionCleanReact(Action):
    def name(self):
        return "action_clean_react"

    def run(self, dispatcher, tracker, domain):
        print("action_clean_react wird gestartet")
        globalLastAction = "clean_react"
        answertype = tracker.latest_message["intent"].get("name")

        print("answertype: " + answertype)

        if tracker.get_slot("proactive_level") is None:
            optionInt = 1
        else:
            optionInt = tracker.get_slot("proactive_level")

        if answertype == "deny":
            print("kein clean")
            optionInt -= 2
            if optionInt <= 0:
                optionInt == 1
            dispatcher.utter_message("Okay, ich überlasse dir den Einkauf.")
            return[SlotSet("confirmed", False), SlotSet("proactive_level", optionInt)]

        elif answertype == "affirm" or answertype == "answer_anom_alt":
            print("verstaut die einkäufe")
            optionInt += 1
            if optionInt >4:
                optionInt == 4
            dispatcher.utter_message("Okay, ich verstaue den Einkauf.")
            return [SlotSet("confirmed", True),FollowupAction("action_clean")]

        else:
            return [SlotSet("confirmed", None)]

        return

class ActionSendClean(Action):
    def name(self):
        return "action_clean"

    def run(self, dispatcher, tracker, domain):
        print("action_clean wird gestartet")

        #furniture = tracker.get_slot('furniture')
        furniture = "Esstisch"
        #if furniture is not None:
            #furniture = furniture.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace(
               # "ü",
               # "ue").replace(
               # "Ü", "Ue")

            #furniture = furniture.lower()

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "clean",
            "parameter": {
                "to": furniture,
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")


        if tracker.get_slot("proactive_level") is None:
            optionInt = 1
        else:
            optionInt = tracker.get_slot("proactive_level")

        return [SlotSet("proactive_level", optionInt), SlotSet("furniture", furniture)]


class ActionSendCommandLfd(Action):
    def name(self):
        return "action_command_lfd"

    def run(self, dispatcher, tracker, domain):
        print("action_command_lfd wird gestartet")

        keyword = tracker.get_slot('keyword')

        if keyword is not None:
            keyword = keyword.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü",
                                                                                                                  "ue").replace(
                "Ü", "Ue")
            keyword = keyword.lower()

        task = tracker.get_slot('task')

        if task is not None:
            task = task.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü",
                                                                                                            "ue").replace(
                "Ü", "Ue")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "lfd",
            "parameter": {
                "keyword": keyword,
                "task": task
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        #if (answer_flag == 1):
        #    answtype = ActionAnswerRobot.run(self, dispatcher, tracker, domain)

        return


class ActionSendReproduceLfd(Action):
    def name(self):
        return "action_reproduce_lfd"

    def run(self, dispatcher, tracker, domain):
        print("action_reproduce_lfd wird gestartet")

        keyword = tracker.get_slot('keyword')
        if keyword is not None:
            keyword = keyword.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü",
                                                                                                                  "ue").replace(
                "Ü", "Ue")
            keyword = keyword.lower()

        task = tracker.get_slot('task')

        if task is not None:
            task = task.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü",
                                                                                                            "ue").replace(
                "Ü", "Ue")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "lfd",
            "parameter": {
                "keyword": keyword,
                "task": task,
                "operation": "reproduce"
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        #if (answer_flag == 1):
        #    answtype = ActionAnswerRobot.run(self, dispatcher, tracker, domain)

        return


class ActionSendStartLfd(Action):
    def name(self):
        return "action_start_lfd"

    def run(self, dispatcher, tracker, domain):
        print("action_start_lfd wird gestartet")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "lfd",
            "parameter": {
                "operation": "start",
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        #if (answer_flag == 1):
        #    answtype = ActionAnswerRobot.run(self, dispatcher, tracker, domain)

        return


class ActionSendStopLFD(Action):
    def name(self):
        return "action_stop_lfd"

    def run(self, dispatcher, tracker, domain):
        print("action_stop_lfd_take wird gestartet")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "lfd",
            "parameter": {
                "operation": "end",
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        #if (answer_flag == 1):
        #    answtype = ActionAnswerRobot.run(self, dispatcher, tracker, domain)

        return


class ActionSendSaveLfd(Action):
    def name(self):
        return "action_save_lfd"

    def run(self, dispatcher, tracker, domain):
        print("action_save_lfd wird gestartet")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "lfd",
            "parameter": {
                "operation": "save",
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        #if (answer_flag == 1):
        #    answtype = ActionAnswerRobot.run(self, dispatcher, tracker, domain)

        return


class ActionSendDeleteLfd(Action):
    def name(self):
        return "action_delete_lfd"

    def run(self, dispatcher, tracker, domain):
        print("action_delete_lfd wird gestartet")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "lfd",
            "parameter": {
                "operation": "delete",
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        #if (answer_flag == 1):
        #    answtype = ActionAnswerRobot.run(self, dispatcher, tracker, domain)

        return


class ActionSendGreet(Action):
    def name(self):
        return "action_greet"

    def run(self, dispatcher, tracker, domain):
        print("action_greet wird gestartet")

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "greet",
            "parameter": {
                "operation": "delete",
            }
        }
        c = json.dumps(b)
        client.publish(topicTask, c)

        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        antwort_str = "actiongreettestdispatch"
        dispatcher.utter_message(antwort_str)

        return


class ActionAskForInfo(Action):

    def name(self):
        return "action_ask_for_info"

    def run(self, dispatcher, tracker, domain):

        global missingInfo
        # missingInfo = "from"  # für interaktives training bitte "entkommentieren"
        print("action_ask_for_info wird gestartet")

        if missingInfo == "from" or missingInfo == "furniture":
            print("parameter: from")
            ask = "Woher soll ich den Gegenstand holen?"
            print(ask)
        elif missingInfo == "object":
            ask = "Was genau soll ich dir bringen?"
        elif missingInfo == "to":
            ask = "Wohin soll ich das bringen?"
        else:
            ask = "Es ist leider ein Fehler aufgetreten. Frag mich bitte noch einmal"

        dispatcher.utter_message(ask)

        return


class ActionBringAfterFrom(Action):

    # Die Action, wenn Kurt nach dem ort fragt, von dem er etwas holen soll. könnte auch integrierbar in die normale
    # bring action sein.

    def name(self):
        return "action_bring_after_from"

    def run(self, dispatcher, tracker, domain):

        print("action_bring_after_from wird gestartet")

        if tracker.get_slot('gegenstand') is not None:
            gegenstand = tracker.get_slot('gegenstand')
        else:
            gegenstand = "Gegenstand nicht definiert"
        # wenn möglich einfach in utf-8 umwandeln
        gegenstand = gegenstand.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "Oe").replace\
            ("ü", "ue").replace("Ü", "Ue")
        gegenstand = gegenstand.lower()
        place = tracker.get_slot('place')
        if place is not None:
            place = place.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü", "ue")\
                .replace("Ü", "Ue")
            place = place.lower()
        else:
            place = tracker.get_slot('furniture')
            if place is None:
                place = ""

        task_id = "TaskID_"

        # Json-file als object erstellen
        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "bring",
            "parameter": {
                "object": gegenstand,
                "from": place,
                "to": "user",
            }
        }

        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # in MQTT verschickt

        # Anzeigen was rausgeschickt wurde
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        gegenstand = str(tracker.get_slot('gegenstand')).title()
        place=  str(tracker.get_slot('place'))
        gender = german_gender_wiki.search(gegenstand)

        if gender == "N" or gender == "M":
            artikel = "dein "
            # SlotSet("artikel", "dein")
        elif gender == "F":
            artikel = "deine "
            # SlotSet("artikel","deine")
        else:
            artikel = "deine "  # da es Mehrzahl sein könnte (Chips)

        checkroom = room_shelf.sort(place) # checkt eine liste für die richtigen präpositionen
        roomGender = german_gender_wiki.search(place)

        if checkroom == "room":
            if roomGender == "N" or roomGender == "M":
                prepo = " aus dem "
            else:
                prepo =" aus der "
        else:
            if roomGender == "N" or roomGender == "M":
                prepo = " von dem "
            else:
                prepo = " von der "

        ans = "Ich hole dir " + artikel + gegenstand + prepo + place.title()

        dispatcher.utter_message(ans)

        return


class ActionAnomalyDetected(Action):

    # TODO: update to real message given by robot

    def name(self):
        return "action_anomaly_detected"

    def run(self, dispatcher, tracker, domain):

        anomtype = tracker.get_slot("anomaly")
        place = tracker.get_slot('furniture')
        alternative1 = tracker.get_slot("alternative_place1")
        alternative2 = tracker.get_slot("alternative_place2")
        # anomtype = "trash"  # für testzwecke und training

        print("action_anomaly_detected wird gestartet")

        print("\n")
        print("Test anomtype: " + anomtype)
        print("\n")

        generic_utter = "Achtung! Ich habe " + anomtype + " auf dem " + place + " gefunden. " + anomtype + " sollte außer Reichweite von Kindern aufbewahrt werden. "

        if tracker.get_slot("proactive_level") is None:
            optionInt = 4  # wenn nicht gesetzt, zufällig
        else:
            optionInt = tracker.get_slot("proactive_level")

        if optionInt == 4:  # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("anomaly option 4 chosen")
            
            dispatcher.utter_message(generic_utter+"Ich habe mich entschieden " + anomtype + " zur "+alternative1+" zu bringen.")

            return [FollowupAction("action_anom_clean"), SlotSet("proactive_level",3)]

        elif optionInt == 3:  # proaktiv, variante 2: ja/nein-antwort

            print("anomaly option 3 chosen")

            dispatcher.utter_message(generic_utter+"Ich kann " + anomtype + " entweder zur " + alternative1 + " oder zum " +alternative2+ " bringen. Wohin soll ich sie bringen?")

        elif optionInt == 2:  # proaktiv, variante 1: option zum aufräumbefehl

            print("anomaly option 2 has been chosen")

            dispatcher.utter_message(generic_utter+"Was soll ich damit machen?")

        elif optionInt == 1:  # reaktiv: nutzer:in gibt befehl, Roboter äußert sich nicht

            print("anomaly option 1 chosen")

            dispatcher.utter_message(generic_utter)

        return


class ActionAnomalyReact(Action):

    # Die Action, die ausgeführt wird, wenn der User auf option 2-4 antwortet

    def name(self):
        return "action_anomaly_react"

    def run(self, dispatcher, tracker, domain):

        global anomtype

        # anomtype = "trash"  # für testzwecke und (interaktives) training

        print("action_anomaly_react wird gestartet")

        answertype = tracker.latest_message["intent"].get("name")

        #optionInt = tracker.get_slot("proactive_level")

        place = tracker.get_slot("place")
        anomaly = tracker.get_slot("anomaly")
        furniture = tracker.get_slot("furniture")

        print("\n")
        print("answertype: " + answertype)

        #Fallunterscheidung: falls irgendwas AUSSER "nicht" oder "nein" im antwortslot steckt, wird aufgeräumt
        if answertype == "deny":
            print("\n")
            print("räumt nicht auf")
           # optionInt -= 2
           #if optionInt <= 0:
               # optionInt == 1
            dispatcher.utter_message("Okay, ich überlasse das dir.")

        else:
            dispatcher.utter_message("Ich bringe die " + anomaly + " vom " + furniture + " zur " + place + ".")
            #optionInt += 1
            #if optionInt > 4:
               # optionInt == 4
            return [FollowupAction("action_anom_clean")]


        return


class ActionAnomalyClean(Action):
    # TH: hab jetzt der übersicht halber eine eigene action erstellt, die den aufräumbefehl der anomalie (müll, zeitung)
    # versendet
    def name(self):
        return "action_anom_clean"

    def run(self,dispatcher, tracker, domain):

        place = tracker.get_slot("place")
        anomaly = tracker.get_slot("anomaly")
        furniture = tracker.get_slot("furniture")

        if place is not None:
            place = place.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü", "ue")\
                .replace("Ü", "Ue")
            place = place.lower()
        else:
            place = ""

        if furniture is not None:
            furniture = furniture.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü", "ue")\
                .replace("Ü", "Ue")
            furniture = furniture.lower()
        else:
            furniture = ""

        #TODO nur für Studie
        place = ""
        furniture = ""
        
        answertype = tracker.latest_message["intent"].get("name")
        # sende type: anomclean an roboter, hier ändern, wie der befehl an den Roboter später heißen soll
        # als Parameter "is" hab ich mal den typ, also Müll oder Zeitung spendiert

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "bring",
            "parameter": {
                "object": anomaly,
                "from": furniture,
                "to": place
            }
        }
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        print("action_anom_clean wird gestartet")

        return

class ActionAssistanceReact(Action):

    # Die Action, die ausgeführt wird, wenn der User auf option 2-4 antwortet

    def name(self):
        return "action_assistance_react"

    def run(self, dispatcher, tracker, domain):

        global anomtype

        # anomtype = "trash"  # für testzwecke und (interaktives) training

        print("action_assistance_react wird gestartet")

        answertype = tracker.latest_message["intent"].get("name")

        #optionInt = tracker.get_slot("proactive_level")
        
        #if optionInt is None:
            #optionInt = 2

        gegenstand = tracker.get_slot("gegenstand")
        alternative = tracker.get_slot("alternatives")
        place = tracker.get_slot("place")
        furniture = tracker.get_slot("furniture")

        print("\n")
        print("answertype: " + answertype)

        #Fallunterscheidung: falls irgendwas AUSSER "nicht" oder "nein" im antwortslot steckt, wird aufgeräumt
        if answertype == "deny":
            print("\n")
            print("räumt nicht auf")
           # optionInt -= 2
            #if optionInt <= 0:
              #  optionInt == 1
            dispatcher.utter_message("Okay, ich überlasse das dir.")

        else:
            if gegenstand is not None and furniture is not None and place is not None:
                dispatcher.utter_message("Ich bringe den Gegenstand " + gegenstand + " vom " + furniture + " zur " + place + ".")
            else:
                dispatcher.utter_message("Ich verstaue den Gegenstand " + gegenstand+".")

            return [FollowupAction("action_assistance_clean")]
        return


class ActionAlternatives(Action):

    def name(self):
        return "action_offer_alternative"

    def run(self, dispatcher, tracker, domain):

        global globalAlternative

        # globalAlternative = "Fanta"  # für interaktives training
        print("action_offer_alternative wird gestartet")

        gegenstand = tracker.get_slot("gegenstand")
        gegenstand.lower()
        pronoun_k = "kein"
        pronoun_w = "welchen"
        alternativeGl = globalAlternative

        # für den Fall, dass die Slots durch External Trigger Intents irgendwann mal gesetzt werden können
        # dann auch bitte "alternative" in den antworten durch "alternativeGl" ersetzen:
        # print("Test alternative " + tracker.get_slot("alternative"))
        # alternativeGL = tracker.get_slot("alternative")
        print("Alternative: " + alternativeGl)
        alternativeGl.lower()

        genderGegenstand = german_gender_wiki.search(gegenstand)
        genderAlternative = german_gender_wiki.search(alternativeGl)

        alternativeGl = alternativeGl.capitalize()

        if genderGegenstand == "M":
            pronoun_k = "keinen "
        elif genderGegenstand == "F":
            pronoun_k = "keine "
        elif genderGegenstand == "N":
            pronoun_k = "kein "

        if genderAlternative == "M":
            pronoun_w = "einen "
        elif genderAlternative == "F":
            pronoun_w = "eine "
        elif genderAlternative == "N":
            pronoun_w = "eines "

        if tracker.get_slot("proactive_level") is None:
            optionInt = 3
        else:
            optionInt = tracker.get_slot("proactive_level")


        if optionInt == 4:
        # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("alternative option 1 chosen")
            dispatcher.utter_message("Es gibt leider " + pronoun_k + gegenstand + ". Es gibt aber noch "+ pronoun_w + alternativeGl +
                                      ". Ich werde dir " + pronoun_w + " holen.")

            return [SlotSet("gegenstand", alternativeGl), FollowupAction("action_bring"), SlotSet("proactive_level",3)]

        elif optionInt == 3:  # proaktiv, variante 2: ja/nein-antwort

            print("alternative option 2 chosen")
            dispatcher.utter_message("Es gibt leider " + pronoun_k + gegenstand + ". Es gibt aber noch "+ pronoun_w  + alternativeGl +
                                     ". Soll ich dir " + pronoun_w + " holen?")
            return
        elif optionInt == 2:  # proaktiv, variante 1: option zum aufräumbefehl

            print("alternative option 3 has been chosen")
            dispatcher.utter_message("Es gibt leider " + pronoun_k + gegenstand + ". Es gibt aber noch "+ pronoun_w  + alternativeGl +
                                     ".")
            return
        elif optionInt == 1:  # reaktiv: nutzer gibt befehl, Roboter äußert sich nicht
            dispatcher.utter_message("Es gibt leider " + pronoun_k + gegenstand + ".")
            print("alternative option 4 chosen")
            return
        return


class ActionAlternativesReact(Action):
    def name(self):
        return "action_alternative_react"

    def run(self, dispatcher, tracker, domain):

        global globalAlternative
        global globalTaskID

        print("action_alternative_react wird gestartet")

        gegenstand = tracker.get_slot("gegenstand")
        confirmation = tracker.get_slot("confirmed")
        print(gegenstand)
        print(confirmation)
        if confirmation is not None:
            gegenstand = None
        answertype = tracker.latest_message["intent"].get("name")

        print("answertype: " + answertype)
        print(gegenstand)

        #if tracker.get_slot("proactive_level") is None:
           # optionInt = randrange(1,4)  # wenn nicht gesetzt, zufällig
        #else:
            #optionInt = tracker.get_slot("proactive_level")

        if answertype == "deny" and gegenstand is not None:
            print("bringt keine alternative")
            optionInt -= 2
           # if optionInt <= 0:
              #  optionInt == 1

            dispatcher.utter_message("Okay, dann überlasse ich es dir.")
            return[SlotSet("gegenstand", None),SlotSet("confirmed", False)]

        elif answertype == "affirm" and gegenstand is not None:
            print("bringt alternative")

            return [SlotSet("gegenstand", globalAlternative), SlotSet("confirmed", True), FollowupAction("action_bring")]

        else:
            return [SlotSet("confirmed", None)]

        return

class ActionMoreInfo(Action):
    def name(self):
        return "action_more_info"

    def run(self, dispatcher, tracker, domain):

        print("action_more_info wird gestartet")
        info_type = ""
        if tracker.latest_message['entities']:
            info_type = tracker.latest_message['entities'][0]['value']

        print(info_type)

        if info_type == "Greifarm":
            dispatcher.utter_message("Fünf Gelenke erlauben mir meinen Arm in verschiedene Richtungen zu bewegen. Zwei Finger, die mit Kraftsensoren ausgestattet sind, erlauben es mir hierbei Gegenstände mit bis zu 3 Kilogramm sicher zu greifen.")
            return[SlotSet("info_type", "Greifarm"), FollowupAction("utter_more_info")]
        elif info_type == "Sensoren":
            dispatcher.utter_message("In meinem Kopf befinden sich verschiedene Sensoren und eine Kamera, mit denen ich mein Umfeld, Abstände, Personen und Objekte erkennen kann. Mit meinen Lautsprechern und Mikrofonen kann ich mit Ihnen kommunizieren. Zusätzlich verfüge ich über einen Laserscanner und Ultraschallsensoren um Kollisionen zu vermeiden.")
            return [SlotSet("info_type", "Sensoren"), FollowupAction("utter_more_info")]
        elif tracker.get_slot("info_type") == "Sensoren":
            dispatcher.utter_message("Fünf Gelenke erlauben mir meinen Arm in verschiedene Richtungen zu bewegen. Zwei Finger, die mit Kraftsensoren ausgestattet sind, erlauben es mir hierbei Gegenstände mit bis zu 3 Kilogramm sicher zu greifen.")
            return [SlotSet("info_type", "Greifarm")]
        elif tracker.get_slot("info_type") == "Greifarm":
            dispatcher.utter_message("In meinem Kopf befinden sich verschiedene Sensoren und eine Kamera, mit denen ich mein Umfeld, Abstände, Personen und Objekte erkennen kann. Mit meinen Lautsprechern und Mikrofonen kann ich mit Ihnen kommunizieren. Zusätzlich verfüge ich über einen Laserscanner und Ultraschallsensoren um Kollisionen zu vermeiden.")
            return [SlotSet("info_type", "Sensoren")]
        return


class ActionMemorize(Action):
    def name(self):
        return "action_memorize"
    def run(self, dispatcher, tracker, domain):

        print("action_memorize wird gestartet.")

        mqttJSON = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "memorize",
            "parameter": {}
        }
        toPublish = json.dumps(mqttJSON)  # Python object in Json convertieren
        client.publish(topicTask, toPublish)
        dispatcher.utter_message("Alles klar, bis später.")
        return

class ActionAssistanceNeeded(Action):
    def name(self):
        return "action_assistance_needed"

    def run(self, dispatcher, tracker, domain):

        print("action_assistance_needed wird gestartet")

        gegenstand = tracker.get_slot("gegenstand")
        alternative = tracker.get_slot("alternatives")
        place = tracker.get_slot("place")

        if tracker.get_slot("proactive_level") is None:
            optionInt = randrange(1,4)
        else:
            optionInt = tracker.get_slot("proactive_level")

        if optionInt == 4:  # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("anomaly option 4 chosen")

            dispatcher.utter_message("Ich weiß nicht wohin der Gegenstand "+gegenstand+" gehört. Ich vermute, dass er zum gleichen Ort"+place+" wie Gegenstand "+alternative+" gehört. Ich werde ihn dorthin bringen.")
            
            return [FollowupAction("action_assistance_clean"), SlotSet("proactive_level",3)]

        elif optionInt == 3:  # proaktiv, variante 2: ja/nein-antwort

            print("anomaly option 3 chosen")

            dispatcher.utter_message("Ich weiß nicht wohin der Gegenstand "+gegenstand+" gehört. Wohin soll ich ihn bringen? Eine Möglichkeit wäre der gleiche Ort"+place+" wie Gegenstand "+alternative+"?")

        elif optionInt == 2:  # proaktiv, variante 1: option zum aufräumbefehl

            print("anomaly option 2 has been chosen")

            dispatcher.utter_message("Ich weiß nicht wohin der Gegenstand "+gegenstand+" gehört. Was soll ich damit machen?")

        elif optionInt == 1:  # reaktiv: nutzer:in gibt befehl, Roboter äußert sich nicht

            print("anomaly option 1 chosen")

            dispatcher.utter_message("Ich weiß nicht wohin der Gegenstand "+gegenstand+" gehört.")

        return

class IncomingSuccessMessage(Action):
    def name(self):
        return "action_success_message"

    def run(self, dispatcher, tracker, domain):

        print("action_success_message wird gestartet")
        success = tracker.get_slot("success")

        if globalLastAction is not None and success is not None:

            if globalLastAction == "anomaly_detected":
                print("incoming anomaly_detected success message")

            elif globalLastAction == "alternatives":
                print("incoming alternatives success message")

            elif globalLastAction == "handover_start":
                print("incoming handover_start success message")
                if success:
                    dispatcher.utter_message("Das Überreichen ist abgeschlossen.")
                else:
                    dispatcher.utter_message("Hoppla, etwas ist falsch gelaufen. Ich kann die Aktion nicht ausführen.")

            elif globalLastAction == "handover_completed":
                print("incoming handover_completed success message")

            elif globalLastAction == "bring":
                print("incoming bring success message")
                if success:
                    print("lol")
                else:
                    dispatcher.utter_message("Hoppla, etwas ist falsch gelaufen. Ich kann die Aktion nicht ausführen.")
            else:
                print("incoming UNDEFINED success message")
                if success:
                    print("lol")
                else:
                    dispatcher.utter_message("Hoppla, etwas ist falsch gelaufen. Ich komme hier nicht weiter, bitte System zurücksetzen.")

        return

class IncomingSuccessMessage(Action):
    def name(self):
        return "action_greet_person"

    def run(self, dispatcher, tracker, domain):

        print ("action_greet_person_is_started")
        
        person_name = tracker.get_slot("name")
        
        if person_name is None:
           person_name = ""
           dispatcher.utter_message("Hallo. Schön dich kennenzulernen.")
        else:
           dispatcher.utter_message("Hallo, " + person_name + ". Schön dich kennenzulernen.")

    return

