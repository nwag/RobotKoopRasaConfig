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
anomtype = None  # Variable, um den Typ der Anomalie später für Fallunterscheidungen zu speichern

answobjects = None

# Die answer_flag bestimmt ob man auf eine Antwort von dem Roboter wartet.
# In der späteren Benutzung wird man immer auf eine Antwort des Roboters warten
# beim entwickeln ist es aber imme ein bischen nervig andauernd mit einem anderen Gerät MQTT-Nachrichten zu verschicken
answer_flag = 1  # 0=wartet auf keine Antwort #1=wartet auf Antwort

client = mqtt.Client("ds")

# für test den Host nehmen
#host_name = "test.mosquitto.org"
# host_name = "mqtt.eclipse.org"
# host_name = "192.168.178.149"
# host_name = "iot.eclipse.org"
host_name = "134.60.153.113"

# für Hochschule Weingarten den folgenden Host und Client nehmen
# host_name="192.168.5.112"
# host_name="192.168.0.124"
# host_name = '0.tcp.eu.ngrok.io'
# client.connect(host_name, 11667, 60)
client.connect(host_name, 1883, 60)

# host_name="iot.eclipse.org" #falls test.mosquitto.org down ist oder nicht funktioniert
# client.connect(host_name)

# inoffizielle topicTask
#topicTask = "test/dialogue/task"
#topicStatus = "test/robots/status"

# Offizielle topicTask
topicTask="/dialogue/task"
topicStatus="/robots/status"
topicRobotTask="/robots/task"
topicDialStatus="/dialogue/status"

client.loop_start()
# client.subscribe(topicTask)#eigentlich "/dialogue/display" #nicht subscriben da der Bot sonst seine eigenen Nachrichten bekommt
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

        # Bot frägt nach fehlender information
        if dson["type"] == "missing_info":
            # {"target_id": "dm", "source_id": "kurt", "timestamp": 1552481472, "task_id":  "task1559481472", "priority": 3, "type": "missing_info", "parameter": {"missing_parameters": "from", "lang": "de_DE"}}
            if "parameter" in dson:

                print("asking for missing location of item")

                if "missing_parameters" in dson["parameter"]:

                    print("missing parameters: ", dson["parameter"]["missing_parameters"])
                    missingInfo = dson["parameter"]["missing_parameters"]

                    #falls noch andere Intents getriggert werden möchten, hier eine Fallunterscheidung
                    if dson["parameter"]["missing_parameters"] == "from":
                        data = '{"name": "EXTERNAL_missing_from"}'
                    elif dson["parameter"]["missing_parameters"] == "object":
                        data = '{"name": "EXTERNAL_missing_from"}'
                    elif dson["parameter"]["missing_parameters"] == "to":
                        data = '{"name": "EXTERNAL_missing_from"}'
                    elif dson["parameter"]["missing_parameters"] == "furniture":
                        data = '{"name": "EXTERNAL_missing_from"}'


                else:
                    print("ERROR: No missing parameters")
            else:
                print("no parameter")


        # Anomalie wie Müll oder Zeitung entdeckt
        elif dson["type"] == "anomaly_detected":
            print("anomaly detected")
            # {"target_id": "dm", "source_id": "kurt", "timestamp": 1552481472, "task_id":  "task1559481472", "priority": 3, "type": "anomaly_detected", "parameter": {"anomaly": "Bleiche", "place": "couchtisch", alternative_places:["Spüle","Mülleimer"]}} Beispielnachricht für Anomalie von kurt (NUR TEST, NICHT FINAL)
            if "parameter" in dson and "anomaly" in dson["parameter"]:
                print("Typ der Anomalie: " + dson["parameter"]["anomaly"])
                anomtype = dson["parameter"]["anomaly"]
                data = '{"name": "EXTERNAL_anomaly_detected", "entities":{"anomaly":"'+dson["parameter"]["anomaly"]+'", "place":"'+dson["parameter"]["place"]+'", "alternative_place1":"'+dson["parameter"]["alternative_places"][0]+'","alternative_place2":"'+dson["parameter"]["alternative_places"][1]+'" }}'

            else:
                print("ERROR")

        # Bot bietet alternative an
        elif dson["type"] == "alternatives":
            # {"target_id": "dm", "source_id": "kurt", "timestamp": 1552481472, "task_id":  "task1559481472", "priority": 3, "type": "offer_alternative", "parameter": {"alternative": "Fanta", "lang": "de_DE"}} Beispielnachricht für Alternative von kurt (NUR TEST, NICHT FINAL)
            print("offering alternative")
            if "parameter" in dson and "alternatives" in dson["parameter"]:
                print("alternative found: " + dson["parameter"]["alternatives"][0])
                data = '{"name": "EXTERNAL_alternative", "entities": {"alternatives": "' + dson["parameter"]["alternatives"][0] + '"}}'
                globalAlternative = dson["parameter"]["alternatives"][0]  # Alternative global setzen
                globalTaskID = dson["task_id"]
                # data = '{"name": "EXTERNAL_alternative", "entities": {"alternative": "Fanta"}}'

            else:
                print("ERROR")

        elif dson["type"] == "tts":
            print("Text To Speech")
            print(dson["parameter"]["text"])

            data = '{"name": "EXTERNAL_tts", "entities": {"tts": "' + dson["parameter"]["text"] + '"}}'


            topublish = makeSuccessJSON(dson)
            client.publish(topicDialStatus, topublish)  # in MQTT verschickt

        elif dson["type"] == "person_detected":
            print("Person Detected")
            print(dson["parameter"]["name"])

            data = '{"name": "EXTERNAL_person_detected", "entities": {"person_detected": "' + dson["parameter"]["name"] + '"}}'

            topublish = makeSuccessJSON(dson)  # Python object in Json convertieren
            client.publish(topicDialStatus, topublish)

        elif dson["type"] == "confirm":
            print("Confirm message received")

        elif dson["type"]  == "success":
            print("Success message received")


        elif dson["type"] == "progress":
            print("Progress message")
            #todo try catch
            performedActions = dson["parameter"]["performed_actions"]
            print(performedActions)

            for a in performedActions:
                if a["action"] == "handover_start":
                    if a["target"] != "user":
                        data = '{"name": "EXTERNAL_handover_start", "entities": {"handover_start": "'+ a["target"]+'"}}'
                    else:
                        data = '{"name": "EXTERNAL_handover_start", "entities": {"handover_start": "' + "mein Lieblingsnutzer" + '"}}'
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
                "from": place,
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

        if tracker.get_slot("proactive_level") is None:
            optionInt = 1
        else:
            optionInt = tracker.get_slot("proactive_level")

        #optionInt += 1
        #if optionInt > 4:
            #optionInt == 4

        return [SlotSet("gegenstand", gegenstand)]




class ActionOfferClean(Action):
    def name(self):
        return "action_offer_clean"

    def run(self, dispatcher, tracker, domain):

        print("action_offer_clean wird gestartet")

        if tracker.get_slot("proactive_level") is None:
            optionInt = randrange(1,3)
        else:
            optionInt = tracker.get_slot("proactive_level")

        if optionInt == 4:  # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("clean option 1 chosen")

            dispatcher.utter_message("Ich habe bemerkt, dass du vom Einkaufen zurück bist. Ich werde ihn jetzt für dich aufräumen")


            return [FollowupAction("action_clean")]

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

        elif answertype == "affirm":
            print("macht clean")
            optionInt += 1
            if optionInt >4:
                optionInt == 4
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
        furniture = "kuechentisch"
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
                "furniture": furniture,
            }
        }  # traget_id: sheep. Da ich aber über unverschlüsselten server sende habe ich sie teebot genannt
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        # dispatcher.utter_template("utter_take", tracker)  # Das der Bot darauf antwortet. Also textnachricht
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")
        dispatcher.utter_message("Okay, ich verstaue den Einkauf.")

        if tracker.get_slot("proactive_level") is None:
            optionInt = 1
        else:
            optionInt = tracker.get_slot("proactive_level")

        optionInt += 1
        if optionInt > 4:
            optionInt == 4

        return [SlotSet("proactive_level", optionInt)]


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
            place = place.replace("ä", "ae").replace("Ä", "Ae").replace("ö", "oe").replace("Ö", "oe").replace("ü", "ue")\
                .replace("Ü", "Ue")
            place = place.lower()

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
        place = tracker.get_slot('place')
        alternative1 = tracker.get_slot("alternative_place1")
        alternative2 = tracker.get_slot("alternative_place2")
        # anomtype = "trash"  # für testzwecke und training

        print("action_anomaly_detected wird gestartet")

        print("\n")
        print("Test anomtype: " + anomtype)
        print("\n")
        if tracker.get_slot("proactive_level") is None:
            optionInt = randrange(2,4)  # wenn nicht gesetzt, zufällig
        else:
            optionInt = tracker.get_slot("proactive_level")

        if optionInt == 4:  # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("anomaly option 4 chosen")


            dispatcher.utter_message("Ich habe "+anomtype+" auf dem "+place+" gefunden. Da "+anomtype+" gefährlich für Kinder ist, habe ich mich entschieden diese zur "+alternative1+" zu bringen.")


            return [FollowupAction("action_anom_clean")]

        elif optionInt == 3:  # proaktiv, variante 2: ja/nein-antwort

            print("anomaly option 3 chosen")

            dispatcher.utter_message(
                "Ich habe " + anomtype + " auf dem " + place + " gefunden. Da " + anomtype + " gefährlich für Kinder ist, würde ich diese entweder zur " + alternative1 + " oder zum " +alternative2+ " bringen. Wohin soll ich sie bringen?")

        elif optionInt == 2:  # proaktiv, variante 1: option zum aufräumbefehl

            print("\n")
            print("anomaly option 2 has been chosen")
            print("\n")

            dispatcher.utter_message(
                "Ich habe " + anomtype + " auf dem " + place + " gefunden. " + anomtype + " ist gefährlich für Kinder.")

        elif optionInt == 1:  # reaktiv: nutzer:in gibt befehl, Roboter äußert sich nicht

            print("\n")
            print("anomaly option 1 chosen")
            print("\n")

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

        optionInt = tracker.get_slot("proactive_level")

        print("\n")
        print("answertype: " + answertype)

        #Fallunterscheidung: falls irgendwas AUSSER "nicht" oder "nein" im antwortslot steckt, wird aufgeräumt
        if answertype == "deny":
            print("\n")
            print("räumt nicht auf")
            optionInt -= 2
            if optionInt <= 0:
                optionInt == 1
            dispatcher.utter_message("Okay, ich überlasse das dir.")

        else:
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
        # sende type: anomclean an roboter, hier ändern, wie der befehl an den Roboter später heißen soll
        # als Parameter "is" hab ich mal den typ, also Müll oder Zeitung spendiert

        b = {
            "target_id": "kurt",
            "source_id": "dm",
            "timestamp": int(time.time()),
            "task_id": "task" + str(int(time.time())),
            "priority": 3,
            "type": "anomclean",
            "parameter": {
                "anomaly": anomaly,
                "place": place
            }
        }
        c = json.dumps(b)  # Python object in Json convertieren
        client.publish(topicTask, c)  # raussenden wohin es gehen soll
        print("\n")
        print("message published: ", c)
        print("message topicTask: ", topicTask)
        print("\n")

        print("action_anom_clean wird gestartet")

        dispatcher.utter_message("Alles klar!")

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
            optionInt = randrange(1,4)
        else:
            optionInt = tracker.get_slot("proactive_level")

        counttime = 0

        if optionInt == 4:
        # proaktiv, variante 3: intervention möglich, roboter räumt von allein auf

            print("alternative option 1 chosen")
            dispatcher.utter_message("Es gibt leider " + pronoun_k + gegenstand + ". Es gibt aber noch "+ pronoun_w + alternativeGl +
                                      ". Ich werde dir " + pronoun_w + " holen.")

            return [SlotSet("gegenstand", alternativeGl), FollowupAction("action_bring")]

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

        if tracker.get_slot("proactive_level") is None:
            optionInt = randrange(1,4)  # wenn nicht gesetzt, zufällig
        else:
            optionInt = tracker.get_slot("proactive_level")

        if answertype == "deny" and gegenstand is not None:
            print("bringt keine alternative")
            optionInt -= 2
            if optionInt <= 0:
                optionInt == 1

            dispatcher.utter_message("Okay, dann überlasse ich es dir.")
            return[SlotSet("gegenstand", None),SlotSet("confirmed", False), SlotSet("proactive_level", optionInt)]

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

class ActionSetProactiveLevel(Action):
    def name(self):
        return "action_set_level"

    def run(self, dispatcher, tracker, domain):

        print("action_set_level wird gestartet")

        proactive_level = tracker.latest_message['entities'][0]['value']

        print(proactive_level)

        if proactive_level == "Kein":
            dispatcher.utter_message("Okay, ich werde nicht autonom handeln.")
            return[SlotSet("proactive_level", 1)]
        elif proactive_level == "Wenig":
            dispatcher.utter_message("Okay, ich werde ein wenig autonom handeln.")
            return[SlotSet("proactive_level", 2)]
        elif proactive_level == "Mittel":
            dispatcher.utter_message("Okay, ich werde autonom handeln.")
            return [SlotSet("proactive_level", 3)]
        elif proactive_level == "Hoch":
            dispatcher.utter_message("Okay, ich werde vollständig autonom handeln.")
            return [SlotSet("proactive_level", 4)]
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

        return