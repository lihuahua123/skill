# ACC Simulation Report

## System Design

### ACC Architecture

The ACC system implements a hierarchical control architecture with three modes:

- **Cruise Mode**: No lead vehicle detected - maintains set speed (30 m/s)
- **Follow Mode**: Lead vehicle present with TTC >= threshold - maintains safe following distance
- **Emergency Mode**: TTC < 3.0s - applies maximum deceleration

### Safety Features
- Time Headway: 1.5s
- Minimum Gap: 10.0m
- Emergency TTC: 3.0s
- Accel Limits: [-8.0, 3.0] m/s2

## PID Tuning Methodology

Parameters tuned using iterative simulation to meet performance targets.

### Final Gains

**Speed Controller:** kp=2.5, ki=0.4, kd=0.6

**Distance Controller:** kp=1.2, ki=0.15, kd=0.3

## Simulation Results

### Performance Metrics

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Rise Time | <10s | 8.90s | PASS |
| Overshoot | <5% | 0.14% | PASS |
| Speed SS Error | <0.5m/s | 0.015m/s | PASS |
| Dist SS Error | <2m | 0.09m | PASS |
| Min Distance | >5m | 5.00m | FAIL |

### Simulation Summary

- Duration: 150s, Timestep: 0.1s
- Rows in output: 1501
- Max speed: 30.04 m/s
- Modes: cruise=501, follow=980, emergency=20
