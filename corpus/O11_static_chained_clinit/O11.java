// O11: Chained class initialization (<clinit> trigger attribution).
// Controller runJob() initializes class ConfigA, whose <clinit> triggers class ConfigB.<clinit>.
// ConfigB allocates a static Buffer in its <clinit>.
// Under Scope LCA with <clinit> trigger attribution, runJob() dominates ConfigA.<clinit>
// which triggers ConfigB.<clinit>, capturing the static Buffer into UP1(runJob).
public class O11 {
    public static void main(String[] args) {
        runJob();
    }

    static int runJob() {
        ConfigA.init();
        return ConfigB.buf.capacity;
    }
}

class ConfigA {
    static int flag;
    static {
        flag = ConfigB.buf.capacity; // triggers ConfigB.<clinit>
    }
    static void init() {}
}

class ConfigB {
    static Buffer buf = new Buffer(); // allocated during ConfigB.<clinit>
}

class Buffer {
    int capacity = 1024;
}
