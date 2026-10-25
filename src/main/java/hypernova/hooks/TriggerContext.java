package hypernova.hooks;

public record TriggerContext(FleetView fleet, String systemId, boolean fromDialog) {
}
