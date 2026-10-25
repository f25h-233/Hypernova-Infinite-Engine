package hypernova.telemetry;

public interface Telemetry {
    void event(String kind, String path, long nanos, String detail);

    void flush();

    int buffered();
}
