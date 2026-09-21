public class E11 {

    static Oops published;

    static void make() {
        Oops o = new Oops();
        synchronized (o) {          // reason 1: used as a monitor
        }
        published = o;              // reason 2: stored to a static field
        throw o;                    // reason 3: thrown
    }

    public static void main(String[] args) {
        try {
            make();
        } catch (Oops e) {
        }
    }
}

class Oops extends RuntimeException { }
