def sort(word):

    notrooms = ["stuhl", "tisch", "sofa", "herd", "kochfeld", "bett"]

    if word not in notrooms:

        return "room"
    else:

        return  "notroom"