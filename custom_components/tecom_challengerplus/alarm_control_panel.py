"""Alarm control panel platform for Tecom ChallengerPlus."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)

from .const import DOMAIN
from .entity import TecomBaseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    count = hub.areas_count
    if count <= 0:
        return
    async_add_entities([TecomAreaAlarm(hub, entry, area=i) for i in range(1, count + 1)])


class TecomAreaAlarm(TecomBaseEntity, AlarmControlPanelEntity):
    """Represents a ChallengerPlus Area."""

    # HA does not expose a DISARM feature flag; disarm support is implicit.
    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY

    def __init__(self, hub, entry, area: int) -> None:
        super().__init__(hub, entry)
        self._hub = hub
        self._area = area
        self._attr_unique_id = f"{entry.entry_id}_area_{area}"
        self._attr_name = f"{self._device_name} Area {area}"

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
