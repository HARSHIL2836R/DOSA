// O06: threads. A Box handed to a Worker thread outlives main's frame for as long as the
// worker holds it, so no frame of either thread owns it. The worker's own scratch Item dies
// with run(); the Item it stores into the shared Box does not.
public class O06 {
    public static void main(String[] args) throws InterruptedException {
        Box shared = new Box();             // S: handed to the worker
        Worker w = new Worker(shared);      // W: the thread object
        w.start();
        w.join();
        Box mine = new Box();               // M: main's own
        mine.item = new Item();             // K: main's own
    }
}

class Worker extends Thread {
    Box b;
    Worker(Box b) { this.b = b; }

    public void run() {
        Item i = new Item();                // P: published into the shared Box
        b.item = i;
        Item j = new Item();                // J: run()'s own
        j.n = 1;
    }
}

class Box  { Item item; }
class Item { int n; }
