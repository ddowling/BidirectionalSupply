# BidirectionalSupply Calibration Results

This directory contains calibration data and analysis results for the BQ25758-based BidirectionalSupply boards.

## Board Comparison Summary

| Parameter | Board 1 (RP2350_B1F4049F) | Board 2 (RP2350_1E017096) | Difference |
|-----------|---------------------------|---------------------------|------------|
| RMS Error | 246.30 mV | 246.30 mV | 0.00 mV |
| Mean Error | -224.52 mV | -224.52 mV | 0.00 mV |
| Max Error | 422.18 mV | 422.18 mV | 0.00 mV |
| Linearity R² | 0.999951 | 0.999951 | 0.000000 |
| Gain | 1.003113 (+0.311%) | 1.003113 (+0.311%) | 0.000000 |
| Offset | -304.7 mV | -304.7 mV | 0.0 mV |

## Key Findings

### 32-33V Transition Point
Both boards exhibit identical dual-range voltage measurement behavior with a sharp transition at 32-33V:
- **Low Range (3.5-32V)**: Higher systematic errors (-400 to -200mV)
- **High Range (33-48V)**: Lower systematic errors (-150 to -80mV)
- This is confirmed to be a BQ25758 chip characteristic, not board-specific

### Board-to-Board Consistency
The two boards show remarkably similar calibration characteristics, suggesting consistent manufacturing and chip behavior.

## Files Description

### Board 1 (RP2350_B1F4049F)
- `board1_voltage_calibration_analysis.png` - 4-panel comprehensive analysis
- `board1_combined_adc_analysis.png` - 2-panel focused analysis  
- `board1_calibration_report.txt` - Statistical summary
- `board1_metadata.json` - Board hardware information

### Board 2 (RP2350_1E017096)  
- `board2_voltage_calibration_analysis.png` - 4-panel comprehensive analysis
- `board2_combined_adc_analysis.png` - 2-panel focused analysis
- `board2_calibration_report.txt` - Statistical summary
- `board2_metadata.json` - Board hardware information

### Analysis Tools
- `analyze_calibration.py` - Original analysis script for Board 1
- `analyze_board2_calibration.py` - Analysis script for Board 2
- `voltage_cal_data.csv` - Raw calibration data (Board 2)
- `README_calibration_analysis.md` - Detailed analysis methodology

## Calibration Strategy

Based on these results, the recommended approach for the 10-board calibration is:

1. **Individual Board Calibration**: Each board requires its own calibration coefficients
2. **Dual-Range Consideration**: May benefit from separate calibration below/above 33V
3. **Systematic Offset Correction**: Primary correction needed is offset (-300mV typical)
4. **Minimal Gain Correction**: Gain error is small (+0.3% typical)

## Test Conditions

- Voltage Range: 3.5V to 48.0V (45 data points)
- Load Condition: 100mA constant load for stable measurements
- Multiple readings per point for statistical analysis
- High-precision reference measurements