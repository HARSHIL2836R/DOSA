public class E08 {

    static Box make() { return new Box(); }   // ONE allocation site

    public static void main(String[] args) {
        Box x = make();
        Box y = make();                       // ... two distinct owners at run time
        Item i = new Item();
        Item j = new Item();
        x.item = i;
        y.item = j;
    }
}

class Box  { Item item; }
class Item { }
