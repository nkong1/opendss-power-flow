#!/usr/bin/env python3
"""
run_power_flow.py

Runs OpenDSS time-series simulation with PV data and custom load profiles.
Separate plotting can be done with plot_results.py

Usage:
    python run_power_flow.py --master raw_data\Master.dss --pv_file raw_data/pv_data_final.xlsx --load_file raw_data\load_timeseries_data.csv --results results --start_hour 1837 --end_hour 1837
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
import json
import opendssdirect as dss


def load_pv_excel(pv_excel_path):
    """
    Load PV data from an .xlsx file.
    Iterates through every sheet and collects rows containing:
    hour_index, bus_id, grid_power_kW (exact names).

    Missing grid_power_kW values are filled with 0.
    """

    p = Path(pv_excel_path)
    if not p.exists():
        raise FileNotFoundError(f"Excel file not found: {pv_excel_path}")

    # Read all sheets
    xls = pd.ExcelFile(p)
    sheet_names = xls.sheet_names

    df_list = []

    for sheet in sheet_names:
        tmp = pd.read_excel(xls, sheet_name=sheet)

        # Ensure required columns exist EXACTLY
        required = ["hour_index", "bus_id", "grid_power_kW"]
        for col in required:
            if col not in tmp.columns:
                raise ValueError(
                    f"Sheet '{sheet}' missing required column '{col}'. "
                    f"Found columns: {tmp.columns.tolist()}"
                )

        # Extract and clean
        tmp = tmp[required].copy()
        tmp["hour_index"] = tmp["hour_index"].astype(int)
        tmp["bus_id"] = tmp["bus_id"].astype(str)
        tmp["grid_power_kW"] = tmp["grid_power_kW"].astype(float).fillna(0) / 1000  # fill missing PV with 0
        # pv_kW is actually given in watts

        df_list.append(tmp)

    # Combine all sheets
    combined = pd.concat(df_list, ignore_index=True)

    # Sort for consistency
    combined = combined.sort_values(["hour_index", "bus_id"]).reset_index(drop=True)

    return combined


def load_load_profiles(load_profile_path):
    """
    Load hourly load profiles from Excel/CSV file.
    Expected format: 
    - Column 0: time_index (15-min intervals, 0 to 35039 for full year)
    - Other columns: bus_id (one column per bus with kW loads)
    
    Returns DataFrame with columns: hour_index, bus_id, load_kW
    """
    p = Path(load_profile_path)
    if not p.exists():
        raise FileNotFoundError(f"Load profile file not found: {load_profile_path}")
    
    # Read file (works for both CSV and Excel)
    if p.suffix == '.csv':
        df = pd.read_csv(p)
    else:
        df = pd.read_excel(p)
    
    # First column should be time_index
    time_col = df.columns[0]
    df = df.rename(columns={time_col: 'time_index'})
    
    # Convert 15-min intervals to hours 
    # time_index 0-3 -> hour 1, 4-7 -> hour 2, etc.
    df['hour_index'] = df['time_index'] // 4 + 1
    
    # Get bus columns (all except time_index and hour_index)
    bus_columns = [col for col in df.columns if col not in ['time_index', 'hour_index']]
    
    # Average load data by hour for each bus
    hourly_loads = df.groupby('hour_index')[bus_columns].mean().reset_index()
    
    # Convert from wide to long format
    load_list = []
    for bus in bus_columns:
        bus_data = hourly_loads[['hour_index', bus]].copy()
        bus_data.columns = ['hour_index', 'load_kW']
        bus_data['bus_id'] = bus
        load_list.append(bus_data)
    
    combined = pd.concat(load_list, ignore_index=True)
    combined = combined[['hour_index', 'bus_id', 'load_kW']]
    combined['load_kW'] = combined['load_kW'].fillna(0.0)
    
    print(f"  Loaded profiles for {len(bus_columns)} buses")
    print(f"  Hours covered: {combined['hour_index'].min()} to {combined['hour_index'].max()}")
    
    return combined


def initialize_dss(master_dss_path):
    """Initialize OpenDSS with master file"""
    if not Path(master_dss_path).exists():
        raise FileNotFoundError(f"Master DSS not found: {master_dss_path}")
    
    dss.Basic.ClearAll()
    dss.Text.Command(f"redirect {master_dss_path}")
    dss.Text.Command("Set mode=snap")
    dss.Text.Command("Set ControlMode=OFF")  # Faster for time series
    return dss


def sanitize_name(name):
    """Create safe name for OpenDSS objects"""
    return str(name).replace('.', '_').replace(' ', '_').replace(':', '_').replace('/', '_')


def create_pv_generators(bus_list, gen_prefix="PV"):
    existing_gens = set([n.lower() for n in dss.Generators.AllNames()])
    gen_map = {}
    
    for bus in bus_list:
        gen_name = f"{gen_prefix}_{sanitize_name(bus)}"
        if gen_name.lower() not in existing_gens:
            # Look up the bus base voltage
            dss.Circuit.SetActiveBus(bus)
            kv_base = dss.Bus.kVBase()  # This is LN voltage in kV
            kv_ll = kv_base * np.sqrt(3)  # Convert to LL for 3-phase generator
            
            cmd = f"New Generator.{gen_name} Bus1={bus}.1.2.3.0 phases=3 kV={kv_ll:.6f} kW=0.0 pf=1.0 Model=1 conn=wye"
            dss.Text.Command(cmd)
        gen_map[bus] = gen_name
    
    return gen_map


def set_generator_kw(gen_name, kw):
    """Set generator kW output"""
    dss.Generators.Name(gen_name)
    dss.Generators.kW(float(kw))


def get_all_load_names():
    """Get all load names in the circuit"""
    return [str(name) for name in dss.Loads.AllNames()]


def set_load_kw(load_name, kw):
    """Set load kW consumption"""
    try:
        dss.Loads.Name(load_name)
        dss.Loads.kW(float(kw))
    except Exception:
        # If load doesn't exist, skip
        pass


def create_load_map(load_buses):
    """
    Create mapping of bus_id to load_name for loads that exist in circuit.
    OpenDSS loads are named like "load_<bus_id>" typically.
    """
    all_loads = get_all_load_names()
    load_map = {}
    
    for load_name in all_loads:
        # Get the bus that this load is connected to
        dss.Loads.Name(load_name)
        bus_name = dss.CktElement.BusNames()[0].split('.')[0]  # Get bus without phase info
        load_map[bus_name] = load_name
    
    return load_map


def get_all_bus_data():
    """Extract all bus data from current solution"""
    bus_data = []
    all_buses = dss.Circuit.AllBusNames()
    
    for bus_name in all_buses:
        dss.Circuit.SetActiveBus(bus_name)
        
        # Get voltage magnitudes and angles (returns [mag1, ang1, mag2, ang2, mag3, ang3])
        pu_volts = dss.Bus.puVmagAngle()
        
        # Extract magnitudes (every other element starting at index 0)
        if pu_volts and len(pu_volts) >= 6:
            mag_a = pu_volts[0]  # Phase A magnitude
            mag_b = pu_volts[2]  # Phase B magnitude
            mag_c = pu_volts[4]  # Phase C magnitude
        elif pu_volts and len(pu_volts) >= 2:
            # Single phase or fewer phases available
            mag_a = pu_volts[0]
            mag_b = pu_volts[2] if len(pu_volts) >= 4 else np.nan
            mag_c = pu_volts[4] if len(pu_volts) >= 6 else np.nan
        else:
            mag_a = mag_b = mag_c = np.nan
        
        # Get distance from substation
        distance = dss.Bus.Distance()
        
        # Get coordinates if available
        x_coord = dss.Bus.X()
        y_coord = dss.Bus.Y()
        voltage_LL = dss.Bus.puVLL()
        kvBase = dss.Bus.kVBase()
        
        bus_data.append({
            'bus': bus_name,
            'pu_a': float(mag_a) if mag_a is not None else np.nan,
            'pu_b': float(mag_b) if mag_b is not None else np.nan,
            'pu_c': float(mag_c) if mag_c is not None else np.nan,
            'distance_km': float(distance) if distance else np.nan,
            'x': float(x_coord) if x_coord else np.nan,
            'y': float(y_coord) if y_coord else np.nan, 
            'kvLL': voltage_LL,
            'kvBase': kvBase
        })
    
    return pd.DataFrame(bus_data)

def get_line_loading():
    """
    Returns a DataFrame with line loading info:
    - line name
    - from bus, to bus
    - active/reactive power (kW, kVar)
    - per-phase current (A)
    - per-phase percent loading
    - max percent loading among phases
    """
    lines_data = []
    all_lines = dss.Lines.AllNames()

    for line in all_lines:
        dss.Lines.Name(line)
        try:
            from_bus, to_bus = dss.Lines.Bus1(), dss.Lines.Bus2()

            # Three-phase power at sending end
            kw = dss.CktElement.Powers()[0] / 1000
            kvar = dss.CktElement.Powers()[1] / 1000

            # Per-phase current magnitudes
            curr_mag = dss.CktElement.CurrentsMagAng()[0::2]  # mag only, per conductor

            # Normalize length to 3 (pad with nan for missing phases)
            I_ph = curr_mag[:3] + [np.nan]*(3-len(curr_mag))
            I1, I2, I3 = I_ph

            # Line ampacity
            amp_rating = dss.Lines.NormAmps()

            # Per-phase % loading
            pct1 = 100*I1/amp_rating if I1 is not None and amp_rating else np.nan
            pct2 = 100*I2/amp_rating if I2 is not None and amp_rating else np.nan
            pct3 = 100*I3/amp_rating if I3 is not None and amp_rating else np.nan

            # Max loading among phases
            max_pct = np.nanmax([pct1, pct2, pct3])

            lines_data.append({
                'line': line,
                'from_bus': from_bus,
                'to_bus': to_bus,
                'kw': kw,
                'kvar': kvar,
                'Iph1_A': I1,
                'Iph2_A': I2,
                'Iph3_A': I3,
                'amp_rating': amp_rating,
                'pct_ph1': pct1,
                'pct_ph2': pct2,
                'pct_ph3': pct3,
                'max_pct_loading': max_pct
            })

        except Exception as e:
            print(f"Warning: failed to get loading for line {line}: {e}")

    return pd.DataFrame(lines_data)


def get_losses_and_generation():
    losses = dss.Circuit.Losses()
    total_loss_kw = losses[0] / 1000
    total_loss_kvar = losses[1] / 1000

    total_pv_kw = 0.0
    for gen in dss.Generators.AllNames():
        dss.Generators.Name(gen)
        total_pv_kw += dss.Generators.kW()

    total_load_kw = 0.0
    for load in dss.Loads.AllNames():
        dss.Loads.Name(load)
        total_load_kw += dss.Loads.kW()

    loss_pct_of_pv = (total_loss_kw / total_pv_kw * 100) if total_pv_kw > 0 else None
    loss_pct_of_load = (total_loss_kw / total_load_kw * 100) if total_load_kw > 0 else None
    
    return {
        'total_loss_kw': total_loss_kw,
        'total_loss_kvar': total_loss_kvar,
        'total_pv_kw': total_pv_kw,
        'total_load_kw': total_load_kw,
        'loss_pct_of_pv': loss_pct_of_pv,
        'loss_pct_of_load': loss_pct_of_load
    }

def run_timeseries(master_dss, pv_df, load_df, results_dir, start_hour=1, end_hour=8760, verbose=False):
    """Run complete time-series simulation"""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize DSS
    print("Initializing OpenDSS...")
    initialize_dss(master_dss)

    # --- Diagnostic: List all buses and their kvbase
    print("=== Bus kvbase summary (first 20) ===")
    for b in dss.Circuit.AllBusNames()[0:20]:
        dss.Circuit.SetActiveBus(b)
        print(b, dss.Bus.kVBase())


    # Configure solution settings
    dss.Text.Command("Set ControlMode=OFF")
    dss.Text.Command("calcv")  # Calculate voltage bases
    
    # Initial solve to establish baseline
    print("Running initial power flow...")
    dss.Solution.Solve()
    
    if not dss.Solution.Converged():
        print("WARNING: Initial solution did not converge!")
        print(f"  Solution mode: {dss.Solution.Mode()}")
        print(f"  Iterations: {dss.Solution.Iterations()}")
        print(f"  Max iterations: {dss.Solution.MaxIterations()}")
        # Try to help convergence
        dss.Text.Command("Set MaxIterations=100")
        dss.Solution.Solve()
        if not dss.Solution.Converged():
            raise RuntimeError("Cannot achieve initial convergence. Check your DSS model.")
    else:
        print("Initial solution converged")
    
    # Create load mapping (bus to load name)
    print("Mapping loads to buses...")
    load_map = create_load_map(load_df['bus_id'].unique())
    print(f"  Found {len(load_map)} loads in circuit")
    
    # Check which load buses are in the circuit
    load_buses_in_data = set(load_df['bus_id'].unique())
    load_buses_in_circuit = set(load_map.keys())
    matched_load_buses = load_buses_in_data & load_buses_in_circuit
    missing_load_buses = load_buses_in_data - load_buses_in_circuit
    
    print(f"  Load buses matched: {len(matched_load_buses)}")
    if missing_load_buses:
        print(f"  Warning: {len(missing_load_buses)} load buses in data not found in circuit")
        if verbose:
            print(f"    Sample missing: {list(missing_load_buses)[:5]}")
    
    # Get PV buses and create generators
    pv_buses = sorted(pv_df['bus_id'].unique())
    print(f"Creating generators for {len(pv_buses)} PV buses...")
    gen_map = create_pv_generators(pv_buses)
    
    # Save generator mapping
    with open(results_dir / "pv_generator_map.json", 'w') as f:
        json.dump(gen_map, f, indent=2)
    
    # Save load mapping
    with open(results_dir / "load_map.json", 'w') as f:
        json.dump(load_map, f, indent=2)
    
    # Get base bus data (coordinates, etc.)
    print("Extracting bus coordinates...")
    base_bus_data = get_all_bus_data()
    
    # Check if we got valid voltage data
    if base_bus_data['pu_a'].isna().all():
        print("⚠ WARNING: All voltage values are NaN. Power flow may not be solving correctly.")
    
    bus_coords = base_bus_data[['bus', 'x', 'y', 'distance_km', 'kvBase', 'kvLL', 'pu_a', 'pu_b', 'pu_c']].copy()
    bus_coords.to_csv(results_dir / "bus_info.csv", index=False)
    
    # Group PV and load data by hour for fast lookup
    pv_grouped = pv_df.groupby('hour_index')
    load_grouped = load_df.groupby('hour_index')
    
    # Storage for all hourly results
    all_hourly_data = []
    convergence_failures = []
    
    # Run simulation for each hour
    hours = range(start_hour, end_hour + 1)
    print(f"Running simulation for hours {start_hour} to {end_hour}...")
    
    pv_buses = []
    all_line_hourly_data = []
    all_loss_data = []

    for hour in tqdm(hours, desc="Solving"):
        
        # Reset all generators to zero
        for gen_name in gen_map.values():
            set_generator_kw(gen_name, 0.0)
        
        # Set PV generation for this hour
        if hour in pv_grouped.groups:
            hour_pv = pv_grouped.get_group(hour)
            for _, row in hour_pv.iterrows():
                bus = row['bus_id']
                pv_buses.append(bus)
                kw = row['grid_power_kW'] 
                if bus in gen_map:
                    set_generator_kw(gen_map[bus], kw)
        
        # Update loads for this hour
        if hour in load_grouped.groups:
            hour_load = load_grouped.get_group(hour)
            for _, row in hour_load.iterrows():
                bus = row['bus_id']
                kw = row['load_kW']
                if bus in load_map:
                    set_load_kw(load_map[bus], kw)
        
        # Solve circuit
        try:
            dss.Solution.Solve()
            
            if not dss.Solution.Converged():
                convergence_failures.append(hour)
                if verbose:
                    print(f"\nWarning: Hour {hour} did not converge (iterations: {dss.Solution.Iterations()})")
        except Exception as e:
            print(f"\nError solving hour {hour}: {e}")
            convergence_failures.append(hour)
            continue
        
        # Extract results
        bus_results = get_all_bus_data()
        bus_results['hour'] = hour
        bus_results['converged'] = dss.Solution.Converged()
        
        # Mark buses with PV and loads
        bus_results['has_pv'] = bus_results['bus'].isin(gen_map.keys())
        bus_results['has_load'] = bus_results['bus'].isin(load_map.keys())
        
        all_hourly_data.append(bus_results)

        # Extract line loading
        line_results = get_line_loading()
        line_results['hour'] = hour
        all_line_hourly_data.append(line_results)

        # Extract loss and generation data
        loss_data = get_losses_and_generation()
        loss_data['hour'] = hour
        loss_data['converged'] = dss.Solution.Converged()
        all_loss_data.append(loss_data)


    # check_pv_buses(pv_buses) for debugging

    # Report convergence issues
    if convergence_failures:
        print(f"\n{len(convergence_failures)} hours failed to converge: {convergence_failures[:10]}{'...' if len(convergence_failures) > 10 else ''}")
    
    # Combine all results
    print("Saving results...")
    combined_results = pd.concat(all_hourly_data, ignore_index=True)
    
    # Save main results file
    combined_results.to_csv(results_dir / "voltage_timeseries.csv", index=False)
    
    # Create summary statistics
    summary = combined_results.groupby('hour').agg({
        'pu_a': ['mean', 'min', 'max'],
        'pu_b': ['mean', 'min', 'max'],
        'pu_c': ['mean', 'min', 'max'],
        'converged': 'first'
    }).reset_index()
    summary.columns = ['_'.join(col).strip('_') for col in summary.columns.values]
    summary.to_csv(results_dir / "voltage_summary.csv", index=False)

    # Combine all hours of line results
    if all_line_hourly_data:
        combined_line_results = pd.concat(all_line_hourly_data, ignore_index=True)
        combined_line_results.to_csv(results_dir / "line_loading_timeseries.csv", index=False)

    # Save metadata
    metadata = {
        'master_dss': str(master_dss),
        'start_hour': start_hour,
        'end_hour': end_hour,
        'total_buses': len(base_bus_data),
        'pv_buses': len(pv_buses),
        'load_buses_matched': len(matched_load_buses),
        'load_buses_missing': len(missing_load_buses),
        'convergence_failures': len(convergence_failures),
        'simulation_complete': True
    }
    with open(results_dir / "simulation_metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n Simulation complete!")
    print(f"  Results saved to: {results_dir}")
    print(f"  Total buses: {len(base_bus_data)}")
    print(f"  PV buses: {len(pv_buses)}")
    print(f"  Load buses (matched): {len(matched_load_buses)}")
    print(f"  Hours simulated: {end_hour - start_hour + 1}")
    print(f"  Convergence rate: {100 * (1 - len(convergence_failures) / len(hours)):.1f}%")
    
    if all_loss_data:
        loss_df = pd.DataFrame(all_loss_data)
        loss_df.to_csv(results_dir / "losses_timeseries.csv", index=False)

        avg_loss_pct_pv = loss_df['loss_pct_of_pv'].dropna().mean()
        avg_loss_pct_load = loss_df['loss_pct_of_load'].dropna().mean()
        print(f"  Avg losses as % of PV generation: {avg_loss_pct_pv:.2f}%")
        print(f"  Avg losses as % of total load: {avg_loss_pct_load:.2f}%")

    return combined_results, summary

def check_pv_buses(pv_buses):
    for bus in pv_buses:
        print(f"\n=== PV Bus: {bus} ===")
        dss.Circuit.SetActiveBus(bus)
    
        # Bus base voltage
        kvbase = dss.Bus.kVBase()
        print(f"Bus kVBase: {kvbase:.4f} kV")
        
        # pu and VLN voltages
        pu_vll = dss.Bus.puVLL()
        vln_v = [abs(v) for v in dss.Bus.Voltages()[0:6:2]]  # Magnitude in volts
        print(f"Bus puVLL: {pu_vll}")
        print(f"Bus VLN magnitudes (V): {vln_v}")
        
        # Active nodes
        nodes = dss.Bus.Nodes()
        print(f"Bus nodes: {nodes}")
        
        # Check generators at this bus
        gens = dss.Bus.AllPCEatBus()
        gen_list = [g for g in gens if "Generator" in g or "pv" in g.lower()]
        for gen_name in gen_list:
            gen_name = gen_name.replace("Generator.", "")
            dss.Generators.Name(gen_name)
            print(f"Generator: {gen_name}")
            print(f"  kW output: {dss.Generators.kW():.2f}")
            print(f"  kVar output: {dss.Generators.kvar():.2f}")
        
        # Upstream transformer (if any)
        lines = dss.Bus.LineList()
        print(f"Connected Lines: {lines}")
        for line in lines:
            line = line.replace("LINE.", "")
            dss.Lines.Name(line)
            print(f"  Line: {line}")
            print(f"    From Bus: {dss.Lines.Bus1()}  To Bus: {dss.Lines.Bus2()}")
            print(f"    Length: {dss.Lines.Length()} {dss.Lines.Units()} units")

def main():
    parser = argparse.ArgumentParser(description='Run OpenDSS PV time-series simulation')
    parser.add_argument('--master', required=True, help='Path to Master.dss file')
    parser.add_argument('--pv_file', required=True, help='Path to PV .xlsx file')
    parser.add_argument('--load_file', required=True, help='Path to load profile file (.xlsx or .csv)')
    parser.add_argument('--results', default='results', help='Output directory')
    parser.add_argument('--start_hour', type=int, default=1, help='Starting hour (0-8759)')
    parser.add_argument('--end_hour', type=int, default=8760, help='Ending hour (0-8759)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Load PV data
    print(f"Loading PV data from {args.pv_file}...")
    pv_df = load_pv_excel(args.pv_file)
    print(f"  Loaded {len(pv_df)} PV records")
    
    # Load load profile data
    print(f"Loading load profiles from {args.load_file}...")
    load_df = load_load_profiles(args.load_file)
    print(f"  Loaded {len(load_df)} load records")
    
    # Run simulation
    run_timeseries(
        args.master,
        pv_df,
        load_df,
        args.results,
        start_hour=args.start_hour,
        end_hour=args.end_hour,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()