// O09: static field written in setup() and read in work(), under controller runSession().
// Both setup() and work() are called exclusively from runSession().
// Under Scope LCA, runSession() dominates all accessors, so setup's allocation is captured
// by runSession() and classified as UP1(runSession).
public class O09 {
    static Session session;

    public static void main(String[] args) {
        runSession(5);
        runSession(10);
    }

    static void runSession(int count) {
        setup();
        work(count);
    }

    static void setup() {
        session = new Session();           // A: allocated in setup, stored into static
        session.item = new Item();         // B: allocated in setup, stored into A.item
    }

    static int work(int count) {
        if (session == null) return 0;
        return session.item.n * count;     // reads static session and session.item
    }
}

class Session { Item item; }
class Item { int n = 7; }
