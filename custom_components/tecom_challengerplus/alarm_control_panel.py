"""Alarm control panel (Areas) for Tecom ChallengerPlus."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]

    # Backwards compatible: use areas_count (1..N). If zero, create none.
    count = int(getattr(hub, "areas_count", 0) or 0)
    if count <= 0:
        return

    entities = [TecomAreaAlarm(hub, area=i) for i in range(1, count + 1)]
    async_add_entities(entities, True)


class TecomAreaAlarm(AlarmControlPanelEntity):
    """Represents one ChallengerPlus Area."""

    _attr_has_entity_name = True
    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY
    _attr_code_arm_required = False
    _attr_code_disarm_required = False

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
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.entry.unique_id or self._hub.entry.entry_id)},
            name=self._hub.entry.title,
            manufacturer="Aritech / Tecom",
            model="ChallengerPlus",
        )

    @property
    def state(self) -> AlarmControlPanelState | None:
        st = self._hub.state.areas.get(self._area)
        if st == "armed":
            return AlarmControlPanelState.ARMED_AWAY
        if st == "disarmed":
            return AlarmControlPanelState.DISARMED
        if st == "alarm":
            return AlarmControlPanelState.TRIGGERED
        return None

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._hub.async_arm_area(self._area)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._hub.async_disarm_area(self._area)
