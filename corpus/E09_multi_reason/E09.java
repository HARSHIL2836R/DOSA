public class E09 {

    static Item published;

    static Item make() {
        Item i = new Item();
        synchronized (i) {          // reason 2: used as a monitor
        }
        published = i;              // reason 1: stored to a static field
        return i;                   // reason 3: returned
    }

    public static void main(String[] args) {
        Item x = make();
    }
}

class Item { }
