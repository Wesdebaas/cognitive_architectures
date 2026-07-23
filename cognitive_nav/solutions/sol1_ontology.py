from owlready2 import *

def load_ontology():

    onto = get_ontology("http://cognitive-nav.org/ontology.owl")

    with onto:
        # Core concepts
        class Room(Thing):
            pass

        class PhysicalObject(Thing):
            pass

        class contains(ObjectProperty):
            domain = [Room]
            range = [PhysicalObject]

        # Objects
        class Sofa(PhysicalObject):
            pass

        class TV(PhysicalObject):
            pass

        class Bed(PhysicalObject):
            pass

        class Chair(PhysicalObject):
            pass

        class DiningTable(PhysicalObject):
            pass

        class Fridge(PhysicalObject):
            pass

        class Cup(PhysicalObject):
            pass

        class Oven(PhysicalObject):
            pass

        # Rooms
        class LivingRoom(Room):
            pass

        class Bedroom(Room):
            pass

        class Kitchen(Room):
            pass

        class DiningRoom(Room):
            pass


        # Classification rules

        # TODO:
        LivingRoom.equivalent_to.append(
            Room
            & contains.some(Cup)
            & contains.some(TV)
        )

        # Bedroom: requires a bed
        Bedroom.equivalent_to.append(
            Room
            & contains.some(Bed)
        )

        # Kitchen: requires a fridge
        Kitchen.equivalent_to.append(
            Room
            & contains.some(Fridge)
        )

        # Dining room: requires a dining table and a chair
        DiningRoom.equivalent_to.append(
            Room
            & contains.some(DiningTable)
            & contains.some(Chair)
        )

    return onto