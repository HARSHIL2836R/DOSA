public class E01 {
    public static void main(String[] args) {
        Box b = new Box();
        Item i = new Item();
        b.item = i;
    }
}

class Box  { Item item; }
class Item { }
