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
        # Add OWL equivalence rules that allow the reasoner
        # to infer the room type from the observed objects.

        # Example:
        LivingRoom.equivalent_to.append(
            Room
            & contains.some(Sofa)
            & contains.some(TV)
        )

        Bedroom.equivalent_to.append(
            Room
            & contains.some(Bed)
        )

        Kitchen.equivalent_to.append(
            Room
            & contains.some(Fridge)
            & contains.some(Oven)
        )

        DiningRoom.equivalent_to.append(
            Room
            & contains.some(DiningTable)
        )

        # Try to make your rules specific enough to avoid
        # confusing one room with another.


    return onto