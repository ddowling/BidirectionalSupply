#!/usr/bin/env python3
"""
Analyze Board 2 ADC calibration data and generate comprehensive plots
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import json

def linear_regression(x, y):
    """Calculate linear regression without scipy"""
    n = len(x)
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    
    # Calculate slope and intercept
    numerator = np.sum((x - x_mean) * (y - y_mean))
    denominator = np.sum((x - x_mean) ** 2)
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    
    # Calculate R-squared
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = 1 - (ss_res / ss_tot)
    
    return slope, intercept, np.sqrt(r_squared)

def analyze_board2_voltage_calibration():
    """Load and analyze Board 2 voltage calibration data"""
    
    # Load voltage calibration data
    df_voltage = pd.read_csv('voltage_cal_data.csv')
    
    # Load board metadata
    with open('board2_metadata.json', 'r') as f:
        metadata = json.load(f)
    
    # Calculate errors
    df_voltage['error_mv'] = (df_voltage['adc_voltage'] - df_voltage['set_voltage']) * 1000
    df_voltage['error_percent'] = (df_voltage['error_mv'] / (df_voltage['set_voltage'] * 1000)) * 100
    
    # Statistical analysis
    mean_error = df_voltage['error_mv'].mean()
    std_error = df_voltage['error_mv'].std()
    rms_error = np.sqrt(np.mean(df_voltage['error_mv']**2))
    max_error = df_voltage['error_mv'].abs().max()
    
    # Linear regression for gain/offset calculation
    slope, intercept, r_value = linear_regression(
        df_voltage['set_voltage'].values, df_voltage['adc_voltage'].values)
    
    print("=" * 60)
    print("Board 2 Voltage ADC Analysis")
    print("=" * 60)
    print(f"Board ID: {metadata['board_id']}")
    print(f"Hardware ID: {metadata['hardware_id']}")
    print(f"Data Points: {len(df_voltage)}")
    print(f"Voltage Range: {df_voltage['set_voltage'].min():.1f}V to {df_voltage['set_voltage'].max():.1f}V")
    print(f"RMS Error: {rms_error:.2f} mV")
    print(f"Max Error: {max_error:.2f} mV")
    print(f"Mean Error: {mean_error:.2f} mV (systematic offset)")
    print(f"Std Error: {std_error:.2f} mV (random variation)")
    print(f"Linearity R²: {r_value**2:.6f}")
    print(f"Gain: {slope:.6f} ({(slope-1)*100:+.3f}%)")
    print(f"Offset: {intercept:.6f} V ({intercept*1000:.1f} mV)")
    
    # Create comprehensive plots
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle(f'Voltage ADC Calibration Analysis - {metadata["board_id"]}', fontsize=16, fontweight='bold')
    
    # Plot 1: ADC Reading vs Set Voltage
    ax1.scatter(df_voltage['set_voltage'], df_voltage['adc_voltage'], alpha=0.7, s=30)
    perfect_line = np.linspace(df_voltage['set_voltage'].min(), df_voltage['set_voltage'].max(), 100)
    ax1.plot(perfect_line, perfect_line, 'r--', alpha=0.8, linewidth=2, label='Perfect calibration')
    ax1.plot(perfect_line, slope * perfect_line + intercept, 'g-', alpha=0.8, linewidth=2, 
             label=f'Fit: y = {slope:.6f}x + {intercept:.6f}')
    ax1.set_xlabel('Set Voltage (V)')
    ax1.set_ylabel('ADC Reading (V)')
    ax1.set_title('ADC Reading vs Set Voltage')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Voltage Error vs Set Voltage
    ax2.scatter(df_voltage['set_voltage'], df_voltage['error_mv'], alpha=0.7, s=30, label='Voltage Error')
    ax2.axhline(y=0, color='r', linestyle='--', alpha=0.8)
    ax2.set_xlabel('Set Voltage (V)')
    ax2.set_ylabel('Error (mV)')
    ax2.set_title('Voltage Error vs Set Voltage')
    ax2.grid(True, alpha=0.3)
    
    # Highlight the 32-33V transition region
    transition_mask = (df_voltage['set_voltage'] >= 32) & (df_voltage['set_voltage'] <= 34)
    if transition_mask.any():
        ax2.scatter(df_voltage.loc[transition_mask, 'set_voltage'], 
                   df_voltage.loc[transition_mask, 'error_mv'], 
                   color='red', s=50, alpha=0.8, label='32-33V Transition')
        ax2.legend()
    
    # Plot 3: Error Distribution
    ax3.hist(df_voltage['error_mv'], bins=15, alpha=0.7, edgecolor='black')
    ax3.axvline(mean_error, color='r', linestyle='--', linewidth=2, 
                label=f'Mean: {mean_error:.1f} mV')
    ax3.axvline(mean_error - std_error, color='orange', linestyle='--', alpha=0.7,
                label=f'±1σ: ±{std_error:.1f} mV')
    ax3.axvline(mean_error + std_error, color='orange', linestyle='--', alpha=0.7)
    ax3.set_xlabel('Error (mV)')
    ax3.set_ylabel('Count')
    ax3.set_title('Error Distribution')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Measurement Stability (Standard Deviation)
    ax4.scatter(df_voltage['set_voltage'], df_voltage['adc_std'] * 1000, alpha=0.7, s=30)
    ax4.set_xlabel('Set Voltage (V)')
    ax4.set_ylabel('Std Deviation (mV)')
    ax4.set_title('Measurement Stability')
    ax4.grid(True, alpha=0.3)
    
    # Highlight transition region in stability plot too
    if transition_mask.any():
        ax4.scatter(df_voltage.loc[transition_mask, 'set_voltage'], 
                   df_voltage.loc[transition_mask, 'adc_std'] * 1000, 
                   color='red', s=50, alpha=0.8, label='32-33V Transition')
        ax4.legend()
    
    plt.tight_layout()
    plt.savefig('board2_voltage_calibration_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # Create combined comparison plot showing the transition clearly
    fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    fig2.suptitle(f'Board 2 ADC Analysis - {metadata["board_id"]}', fontsize=16, fontweight='bold')
    
    # Voltage ADC Error
    ax1.scatter(df_voltage['set_voltage'], df_voltage['error_mv'], alpha=0.7, s=30)
    ax1.axhline(y=0, color='r', linestyle='--', alpha=0.8)
    ax1.set_xlabel('Set Voltage (V)')
    ax1.set_ylabel('Error (mV)')
    ax1.set_title('Voltage ADC Error')
    ax1.grid(True, alpha=0.3)
    
    # Add vertical lines at transition point
    ax1.axvline(x=32, color='purple', linestyle=':', alpha=0.7, label='Transition Region')
    ax1.axvline(x=33, color='purple', linestyle=':', alpha=0.7)
    ax1.legend()
    
    # Voltage Linearity Analysis
    ax2.scatter(df_voltage['set_voltage'], df_voltage['adc_voltage'], alpha=0.7, s=30, label='Data')
    perfect_line = np.linspace(df_voltage['set_voltage'].min(), df_voltage['set_voltage'].max(), 100)
    ax2.plot(perfect_line, perfect_line, 'r--', alpha=0.8, linewidth=2, label='Perfect (1:1)')
    ax2.plot(perfect_line, slope * perfect_line + intercept, 'g-', alpha=0.8, linewidth=2,
             label=f'Fit: y = {slope:.6f}x + {intercept:.3f}')
    ax2.set_xlabel('Set Voltage (V)')
    ax2.set_ylabel('ADC Voltage (V)')
    ax2.set_title('Voltage Linearity Analysis')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('board2_combined_adc_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    return df_voltage, metadata, {
        'mean_error': mean_error,
        'std_error': std_error,
        'rms_error': rms_error,
        'max_error': max_error,
        'r_squared': r_value**2,
        'gain': slope,
        'offset': intercept
    }

if __name__ == "__main__":
    df_voltage, metadata, stats = analyze_board2_voltage_calibration()
    
    # Generate a calibration report
    with open('board2_calibration_report.txt', 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("BidirectionalSupply Board 2 ADC Calibration Report\n")
        f.write("=" * 60 + "\n")
        f.write(f"Board ID: {metadata['board_id']}\n")
        f.write(f"Hardware ID: {metadata['hardware_id']}\n")
        f.write(f"Calibration Date: {metadata.get('calibration_date', 'not_calibrated')}\n")
        f.write("\n")
        f.write("VOLTAGE ADC ANALYSIS:\n")
        f.write("-" * 30 + "\n")
        f.write(f"Data Points: {len(df_voltage)}\n")
        f.write(f"Voltage Range: {df_voltage['set_voltage'].min():.1f}V to {df_voltage['set_voltage'].max():.1f}V\n")
        f.write(f"RMS Error: {stats['rms_error']:.2f} mV\n")
        f.write(f"Max Error: {stats['max_error']:.2f} mV\n")
        f.write(f"Mean Error: {stats['mean_error']:.2f} mV (systematic offset)\n")
        f.write(f"Std Error: {stats['std_error']:.2f} mV (random variation)\n")
        f.write(f"Linearity R²: {stats['r_squared']:.6f}\n")
        f.write(f"Gain: {stats['gain']:.6f} ({(stats['gain']-1)*100:+.3f}%)\n")
        f.write(f"Offset: {stats['offset']:.6f} V ({stats['offset']*1000:.1f} mV)\n")
        f.write("\n")
        f.write("Files generated:\n")
        f.write("- board2_voltage_calibration_analysis.png\n")
        f.write("- board2_combined_adc_analysis.png\n")
        f.write("- board2_calibration_report.txt\n")
    
    print(f"\nCalibration report saved to board2_calibration_report.txt")