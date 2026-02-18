"""Alarm control panel entities for areas."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelState,
    AlarmControlPanelEntityFeature,
)

from .const import DOMAIN
from .exceptions import TecomNotSupported

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    entities = [TecomAreaAlarm(hub, i) for i in range(1, hub.areas_count + 1)]
    async_add_entities(entities, True)

class TecomAreaAlarm(AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY | AlarmControlPanelEntityFeature.DISARM
    _attr_icon = "mdi:shield-home"

    def __init__(self, hub, area: int) -> None:
        self._hub = hub
        self._area = area
        self._attr_name = f"Area {area}"
        self._attr_unique_id = f"{hub.entry.entry_id}_area_{area}"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self._hub.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def state(self):
        raw = self._hub.state.areas.get(self._area)
        if raw == "armed":
            return AlarmControlPanelState.ARMED_AWAY
        if raw == "disarmed":
            return AlarmControlPanelState.DISARMED
        if raw == "alarm":
            return AlarmControlPanelState.TRIGGERED
        return AlarmControlPanelState.UNKNOWN

    async def async_alarm_disarm(self, code=None):
        if self._hub.mode != "ctplus":
            raise TecomNotSupported("Area control requires CTPlus/management mode")
        await self._hub.async_disarm_area(self._area)

    async def async_alarm_arm_away(self, code=None):
        await self._hub.async_arm_area(self._area)
