public class E06 {

    static void fill(Box box) {
        Item i = new Item();
        box.item = i;          // stored into a field of a PARAMETER
    }

    public static void main(String[] args) {
        Box b = new Box();
        fill(b);
    }
}

class Box  { Item item; }
class Item { }
