# Water Source Proximity Camera

Exploration now adds a restrained proximity zoom around working water stations. The camera reads Jack's world-space distance to the nearest eligible station and applies a smooth multiplier to the existing follow or overview shot.

## Runtime Contract

- Every `water_station` object contributes, including a currently stopped station.
- The influence eases from zero at 160 world units to full strength at 56 world units.
- Full influence is a `1.14` zoom multiplier.
- Spatial falloff uses smoothstep; temporal motion uses exponential smoothing.
- Approach uses a 0.75 second time constant and departure uses a slower 1.05 second time constant.
- Focus shots retain their existing authored zoom.
- Combat continues to use its captured entry zoom and existing combat camera multipliers.
- No player, interaction, or world coordinates are changed.
