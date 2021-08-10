import requests

def search(word):

    word=word.title()#The first Charakter of the word always need to be capitalized otherwise the wiktionary will not work
    try:
        url='https://de.wiktionary.org/wiki/'+word
        response=requests.get(url)#The whole website will be uploaded in python
        
        
        text=response.text#Convert the website into text
        gender_index=text.index("Genus:")#The word "Genus" gets searched on the website. The fist hit will be taken becaus mostly the genus stands in the Title
        
        gender=text[gender_index+7:gender_index+8]#The first letter of the genus/gender will be stored
        #print("Gender=",gender)
        
        if(gender=="N" or gender=="F" or gender=="M"): #If there will be N=Neutral, F=Femal/Weiblich or M=Male/Männlich it returns the first letter of the gender
            return gender
            
        else:#If there is an error it will return E=Error
            print("Error")
            return "E"
        
    except:
        print("\n")
        print("Unfortunately no article could be found for the word. It is possible that there is no Wiktionary article about this word or you misspelled the word")
        return "E" #There is a error so it will return E=Error
    

