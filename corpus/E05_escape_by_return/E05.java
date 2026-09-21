public class E05 {

    static Box make() {
        Box b = new Box();
        return b;              // the only escape route in the program
    }

    public static void main(String[] args) {
        Box r = make();
    }
}

class Box { Item item; }
class Item { }
