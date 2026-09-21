public class E10 {

    static Item published;

    static void statik() {
        Item a = new Item();
        published = a;              // STATIC_FIELD_STORE, and nothing else
    }

    static void monitor() {
        Item b = new Item();
        synchronized (b) {          // MONITOR, and nothing else
        }
    }

    static void thrown() {
        Oops c = new Oops();
        throw c;                    // THROWN, and nothing else
    }

    public static void main(String[] args) {
        statik();
        monitor();
        try {
            thrown();
        } catch (Oops e) {
        }
    }
}

class Item { }

class Oops extends RuntimeException { }
