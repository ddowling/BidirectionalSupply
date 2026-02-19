#!/usr/bin/env python3
# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
"""
BidirectionalSupply Calibration Data Analysis

This script analyzes detailed calibration data exported from the MicroPython
board and creates matplotlib visualizations.

Usage:
    python analyze_calibration.py

Requirements:
    pip install matplotlib numpy pandas

Files expected:
    - voltage_cal_data.csv (from detailed_calibration.py)
    - current_cal_data.csv (optional, from detailed_calibration.py)  
    - calibration_metadata.json (from detailed_calibration.py)
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import json
import os
from pathlib import Path

def load_voltage_data(filename="voltage_cal_data.csv"):
    """Load voltage calibration data from CSV"""
    if not os.path.exists(filename):
        print(f"Warning: {filename} not found")
        return None
    
    df = pd.read_csv(filename)
    print(f"Loaded {len(df)} voltage data points from {filename}")
    return df

def load_current_data(filename="current_cal_data.csv"):
    """Load current calibration data from CSV"""
    if not os.path.exists(filename):
        print(f"Warning: {filename} not found")
        return None
    
    df = pd.read_csv(filename)
    
    # Parse the semicolon-separated readings
    df['current_readings_list'] = df['i_readings'].apply(
        lambda x: [float(v) for v in x.split(';')] if pd.notna(x) else []
    )
    df['voltage_readings_list'] = df['v_readings'].apply(
        lambda x: [float(v) for v in x.split(';')] if pd.notna(x) else []
    )
    
    print(f"Loaded {len(df)} current data points from {filename}")
    return df

def load_metadata(filename="calibration_metadata.json"):
    """Load calibration metadata"""
    if not os.path.exists(filename):
        print(f"Warning: {filename} not found")
        return {}
    
    with open(filename, 'r') as f:
        metadata = json.load(f)
    
    print(f"Loaded metadata for board: {metadata.get('board_id', 'unknown')}")
    return metadata

def plot_voltage_calibration(df_voltage, metadata):
    """Create voltage calibration analysis plots"""
    if df_voltage is None:
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f'Voltage ADC Calibration Analysis - {metadata.get("board_id", "Unknown Board")}', fontsize=14)
    
    # Plot 1: Set vs ADC voltage
    axes[0,0].scatter(df_voltage['set_voltage'], df_voltage['adc_voltage'], alpha=0.7, s=30)
    axes[0,0].plot([df_voltage['set_voltage'].min(), df_voltage['set_voltage'].max()], 
                   [df_voltage['set_voltage'].min(), df_voltage['set_voltage'].max()], 
                   'r--', label='Perfect calibration')
    axes[0,0].set_xlabel('Set Voltage (V)')
    axes[0,0].set_ylabel('ADC Reading (V)')
    axes[0,0].set_title('ADC Reading vs Set Voltage')
    axes[0,0].legend()
    axes[0,0].grid(True, alpha=0.3)
    
    # Plot 2: Error vs voltage
    axes[0,1].scatter(df_voltage['set_voltage'], df_voltage['error_mv'], alpha=0.7, s=30)
    axes[0,1].axhline(y=0, color='r', linestyle='--', alpha=0.7)
    axes[0,1].set_xlabel('Set Voltage (V)')
    axes[0,1].set_ylabel('Error (mV)')
    axes[0,1].set_title('Voltage Error vs Set Voltage')
    axes[0,1].grid(True, alpha=0.3)
    
    # Plot 3: Error histogram
    axes[1,0].hist(df_voltage['error_mv'], bins=20, alpha=0.7, edgecolor='black')
    axes[1,0].set_xlabel('Error (mV)')
    axes[1,0].set_ylabel('Count')
    axes[1,0].set_title('Error Distribution')
    axes[1,0].grid(True, alpha=0.3)
    
    # Plot 4: Measurement stability
    axes[1,1].scatter(df_voltage['set_voltage'], df_voltage['adc_std']*1000, alpha=0.7, s=30)
    axes[1,1].set_xlabel('Set Voltage (V)')
    axes[1,1].set_ylabel('Std Deviation (mV)')
    axes[1,1].set_title('Measurement Stability')
    axes[1,1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Calculate and display statistics
    rms_error = np.sqrt(np.mean(df_voltage['error_mv']**2))
    max_error = np.max(np.abs(df_voltage['error_mv']))
    mean_error = np.mean(df_voltage['error_mv'])
    
    stats_text = f'Statistics:\\nRMS Error: {rms_error:.1f} mV\\nMax Error: {max_error:.1f} mV\\nMean Error: {mean_error:.1f} mV'
    fig.text(0.02, 0.02, stats_text, fontsize=10, verticalalignment='bottom',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.savefig('voltage_calibration_analysis.png', dpi=300, bbox_inches='tight')
    print("Saved: voltage_calibration_analysis.png")
    
    return fig

def plot_current_calibration(df_current, metadata):
    """Create current calibration analysis plots"""
    if df_current is None:
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f'Current ADC Calibration Analysis - {metadata.get("board_id", "Unknown Board")}', fontsize=14)
    
    # Plot 1: Set vs ADC current
    axes[0,0].scatter(df_current['set_current'], df_current['adc_current'], alpha=0.7, s=30)
    axes[0,0].plot([df_current['set_current'].min(), df_current['set_current'].max()], 
                   [df_current['set_current'].min(), df_current['set_current'].max()], 
                   'r--', label='Perfect calibration')
    axes[0,0].set_xlabel('Set Current (A)')
    axes[0,0].set_ylabel('ADC Reading (A)')
    axes[0,0].set_title('ADC Reading vs Set Current')
    axes[0,0].legend()
    axes[0,0].grid(True, alpha=0.3)
    
    # Plot 2: Error vs current
    axes[0,1].scatter(df_current['set_current'], df_current['current_error_ma'], alpha=0.7, s=30)
    axes[0,1].axhline(y=0, color='r', linestyle='--', alpha=0.7)
    axes[0,1].set_xlabel('Set Current (A)')
    axes[0,1].set_ylabel('Error (mA)')
    axes[0,1].set_title('Current Error vs Set Current')
    axes[0,1].grid(True, alpha=0.3)
    
    # Plot 3: Power vs current
    axes[1,0].scatter(df_current['set_current'], df_current['power'], alpha=0.7, s=30)
    axes[1,0].set_xlabel('Set Current (A)')
    axes[1,0].set_ylabel('Power (W)')
    axes[1,0].set_title('Power Dissipation vs Current')
    axes[1,0].grid(True, alpha=0.3)
    
    # Plot 4: Measurement stability
    axes[1,1].scatter(df_current['set_current'], df_current['current_std']*1000, alpha=0.7, s=30)
    axes[1,1].set_xlabel('Set Current (A)')
    axes[1,1].set_ylabel('Std Deviation (mA)')
    axes[1,1].set_title('Current Measurement Stability')
    axes[1,1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Calculate and display statistics
    rms_error = np.sqrt(np.mean(df_current['current_error_ma']**2))
    max_error = np.max(np.abs(df_current['current_error_ma']))
    mean_error = np.mean(df_current['current_error_ma'])
    
    stats_text = f'Statistics:\\nRMS Error: {rms_error:.1f} mA\\nMax Error: {max_error:.1f} mA\\nMean Error: {mean_error:.1f} mA'
    fig.text(0.02, 0.02, stats_text, fontsize=10, verticalalignment='bottom',
             bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
    
    plt.savefig('current_calibration_analysis.png', dpi=300, bbox_inches='tight')
    print("Saved: current_calibration_analysis.png")
    
    return fig

def plot_combined_analysis(df_voltage, df_current, metadata):
    """Create combined voltage and current analysis"""
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f'Combined ADC Analysis - {metadata.get("board_id", "Unknown Board")}', fontsize=14)
    
    if df_voltage is not None:
        # Voltage error plot
        axes[0,0].scatter(df_voltage['set_voltage'], df_voltage['error_mv'], 
                         alpha=0.7, s=30, label='Voltage Error', color='blue')
        axes[0,0].axhline(y=0, color='r', linestyle='--', alpha=0.7)
        axes[0,0].set_xlabel('Set Voltage (V)')
        axes[0,0].set_ylabel('Error (mV)')
        axes[0,0].set_title('Voltage ADC Error')
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # Voltage linearity
        x_fit = df_voltage['set_voltage']
        y_fit = df_voltage['adc_voltage']
        coeffs = np.polyfit(x_fit, y_fit, 1)
        y_pred = np.polyval(coeffs, x_fit)
        
        axes[0,1].scatter(x_fit, y_fit, alpha=0.7, s=30, label='Data')
        axes[0,1].plot(x_fit, y_pred, 'r-', label=f'Fit: y={coeffs[0]:.6f}x+{coeffs[1]:.6f}')
        axes[0,1].set_xlabel('Set Voltage (V)')
        axes[0,1].set_ylabel('ADC Voltage (V)')
        axes[0,1].set_title('Voltage Linearity Analysis')
        axes[0,1].legend()
        axes[0,1].grid(True, alpha=0.3)
    
    if df_current is not None:
        # Current error plot
        axes[1,0].scatter(df_current['set_current'], df_current['current_error_ma'], 
                         alpha=0.7, s=30, label='Current Error', color='green')
        axes[1,0].axhline(y=0, color='r', linestyle='--', alpha=0.7)
        axes[1,0].set_xlabel('Set Current (A)')
        axes[1,0].set_ylabel('Error (mA)')
        axes[1,0].set_title('Current ADC Error')
        axes[1,0].legend()
        axes[1,0].grid(True, alpha=0.3)
        
        # Current linearity
        x_fit = df_current['set_current']
        y_fit = df_current['adc_current']
        coeffs = np.polyfit(x_fit, y_fit, 1)
        y_pred = np.polyval(coeffs, x_fit)
        
        axes[1,1].scatter(x_fit, y_fit, alpha=0.7, s=30, label='Data')
        axes[1,1].plot(x_fit, y_pred, 'r-', label=f'Fit: y={coeffs[0]:.6f}x+{coeffs[1]:.6f}')
        axes[1,1].set_xlabel('Set Current (A)')
        axes[1,1].set_ylabel('ADC Current (A)')
        axes[1,1].set_title('Current Linearity Analysis')
        axes[1,1].legend()
        axes[1,1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('combined_adc_analysis.png', dpi=300, bbox_inches='tight')
    print("Saved: combined_adc_analysis.png")
    
    return fig

def generate_calibration_report(df_voltage, df_current, metadata):
    """Generate a comprehensive calibration report"""
    report_lines = []
    
    report_lines.append("=" * 60)
    report_lines.append("BidirectionalSupply ADC Calibration Report")
    report_lines.append("=" * 60)
    
    # Board information
    report_lines.append(f"Board ID: {metadata.get('board_id', 'Unknown')}")
    report_lines.append(f"Hardware ID: {metadata.get('hardware_id', 'Unknown')}")
    report_lines.append(f"Calibration Date: {metadata.get('calibration_date', 'Unknown')}")
    report_lines.append("")
    
    # Voltage analysis
    if df_voltage is not None:
        report_lines.append("VOLTAGE ADC ANALYSIS:")
        report_lines.append("-" * 30)
        
        rms_error = np.sqrt(np.mean(df_voltage['error_mv']**2))
        max_error = np.max(np.abs(df_voltage['error_mv']))
        mean_error = np.mean(df_voltage['error_mv'])
        std_error = np.std(df_voltage['error_mv'])
        
        report_lines.append(f"Data Points: {len(df_voltage)}")
        report_lines.append(f"Voltage Range: {df_voltage['set_voltage'].min():.1f}V to {df_voltage['set_voltage'].max():.1f}V")
        report_lines.append(f"RMS Error: {rms_error:.2f} mV")
        report_lines.append(f"Max Error: {max_error:.2f} mV")
        report_lines.append(f"Mean Error: {mean_error:.2f} mV (systematic offset)")
        report_lines.append(f"Std Error: {std_error:.2f} mV (random variation)")
        
        # Linearity analysis
        x_fit = df_voltage['set_voltage']
        y_fit = df_voltage['adc_voltage']
        coeffs = np.polyfit(x_fit, y_fit, 1)
        r_squared = np.corrcoef(x_fit, y_fit)[0,1]**2
        
        report_lines.append(f"Linearity R²: {r_squared:.6f}")
        report_lines.append(f"Gain: {coeffs[0]:.6f} ({(coeffs[0]-1)*100:+.3f}%)")
        report_lines.append(f"Offset: {coeffs[1]:.6f} V ({coeffs[1]*1000:.1f} mV)")
        report_lines.append("")
    
    # Current analysis
    if df_current is not None:
        report_lines.append("CURRENT ADC ANALYSIS:")
        report_lines.append("-" * 30)
        
        rms_error = np.sqrt(np.mean(df_current['current_error_ma']**2))
        max_error = np.max(np.abs(df_current['current_error_ma']))
        mean_error = np.mean(df_current['current_error_ma'])
        std_error = np.std(df_current['current_error_ma'])
        
        report_lines.append(f"Data Points: {len(df_current)}")
        report_lines.append(f"Current Range: {df_current['set_current'].min():.2f}A to {df_current['set_current'].max():.2f}A")
        report_lines.append(f"RMS Error: {rms_error:.2f} mA")
        report_lines.append(f"Max Error: {max_error:.2f} mA")
        report_lines.append(f"Mean Error: {mean_error:.2f} mA (systematic offset)")
        report_lines.append(f"Std Error: {std_error:.2f} mA (random variation)")
        
        # Power analysis
        max_power = df_current['power'].max()
        report_lines.append(f"Max Power Tested: {max_power:.1f} W")
        
        # Linearity analysis
        x_fit = df_current['set_current']
        y_fit = df_current['adc_current']
        coeffs = np.polyfit(x_fit, y_fit, 1)
        r_squared = np.corrcoef(x_fit, y_fit)[0,1]**2
        
        report_lines.append(f"Linearity R²: {r_squared:.6f}")
        report_lines.append(f"Gain: {coeffs[0]:.6f} ({(coeffs[0]-1)*100:+.3f}%)")
        report_lines.append(f"Offset: {coeffs[1]:.6f} A ({coeffs[1]*1000:.1f} mA)")
        report_lines.append("")
    
    # ADC offset correlation analysis
    if df_voltage is not None and df_current is not None:
        report_lines.append("ADC OFFSET CORRELATION:")
        report_lines.append("-" * 30)
        
        v_coeffs = np.polyfit(df_voltage['set_voltage'], df_voltage['adc_voltage'], 1)
        i_coeffs = np.polyfit(df_current['set_current'], df_current['adc_current'], 1)
        
        v_offset_mv = v_coeffs[1] * 1000
        i_offset_mv = i_coeffs[1] * 5.0  # Convert to mV across 5mΩ shunt
        
        report_lines.append(f"Voltage ADC offset: {v_offset_mv:.1f} mV")
        report_lines.append(f"Current ADC offset: {i_offset_mv:.3f} mV equivalent at shunt")
        report_lines.append(f"Offset ratio: {abs(v_offset_mv/i_offset_mv):.0f}:1" if i_offset_mv != 0 else "Offset ratio: N/A")
        report_lines.append("")
    
    report_lines.append("Files generated:")
    report_lines.append("- voltage_calibration_analysis.png")
    report_lines.append("- current_calibration_analysis.png") 
    report_lines.append("- combined_adc_analysis.png")
    report_lines.append("- calibration_report.txt")
    
    # Save report
    with open('calibration_report.txt', 'w') as f:
        f.write('\\n'.join(report_lines))
    
    # Also print to console
    print("\\n".join(report_lines))
    print("\\nReport saved: calibration_report.txt")

def main():
    """Main analysis function"""
    print("BidirectionalSupply Calibration Analysis")
    print("=" * 50)
    
    # Load data files
    metadata = load_metadata()
    df_voltage = load_voltage_data()
    df_current = load_current_data()
    
    if df_voltage is None and df_current is None:
        print("Error: No calibration data files found!")
        print("Expected files: voltage_cal_data.csv and/or current_cal_data.csv")
        return
    
    # Create plots
    print("\\nGenerating analysis plots...")
    
    if df_voltage is not None:
        plot_voltage_calibration(df_voltage, metadata)
    
    if df_current is not None:
        plot_current_calibration(df_current, metadata)
    
    if df_voltage is not None or df_current is not None:
        plot_combined_analysis(df_voltage, df_current, metadata)
    
    # Generate report
    print("\\nGenerating calibration report...")
    generate_calibration_report(df_voltage, df_current, metadata)
    
    print("\\nAnalysis complete! Check the generated PNG files and report.")

if __name__ == "__main__":
    main()