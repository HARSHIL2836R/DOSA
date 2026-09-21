public class E02 {

    static Box published;

    public static void main(String[] args) {
        Box b = new Box();
        Item i = new Item();
        b.item = i;
        published = b;      // the only difference from E01
    }
}

class Box  { Item item; }
class Item { }
