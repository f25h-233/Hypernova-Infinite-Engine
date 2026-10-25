package hypernova.telemetry;

public interface TelemetrySink {
    void write(String name, String content) throws Exception;
}
