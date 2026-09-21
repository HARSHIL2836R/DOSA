public class E03 {

    static Box published;

    public static void main(String[] args) {
        Box kept = new Box();          // group 1 - stays local
        Item tucked = new Item();
        kept.item = tucked;

        Box leaked = new Box();        // group 2 - identical shape, but published
        Item exposed = new Item();
        leaked.item = exposed;
        published = leaked;
    }
}

class Box  { Item item; }
class Item { }
