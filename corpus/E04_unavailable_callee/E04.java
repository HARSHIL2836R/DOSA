public class E04 {

    // No body. Soot has no summary for it, so the callee is UNAVAILABLE and the
    // status of anything passed to it must stay a conditional value <u,x>.
    static native void sink(Box b);

    public static void main(String[] args) {
        Box b = new Box();
        sink(b);
    }
}

class Box { Item item; }
class Item { }
