import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import re

# Paths
timeseries_csv = "results/voltage_timeseries.csv"
lines_path = "raw_data/Lines.dss"

# Substation coordinates
SUB_BUS = "24ab4116-d257-41b1-960b-481ced9684f1"
SUB_LAT = 34.67381297784516
SUB_LON = -82.83387399502244

# Helpers
def strip_phase_suffix(bus):
    return bus.split(".")[0]


# Load line connectivity
line_segments = []
with open(lines_path, "r") as f:
    for line in f:
        if not line.lower().startswith("new line"):
            continue

        m1 = re.search(r"bus1=([\w\-\.]+)", line, re.IGNORECASE)
        m2 = re.search(r"bus2=([\w\-\.]+)", line, re.IGNORECASE)
        if not (m1 and m2):
            continue

        bus1 = strip_phase_suffix(m1.group(1))
        bus2 = strip_phase_suffix(m2.group(1))
        line_segments.append((bus1, bus2))

print(f"Loaded {len(line_segments)} line segments.")


# Load timeseries data
df = pd.read_csv(timeseries_csv)
df['bus'] = df['bus'].apply(strip_phase_suffix)


# Plotting function
def plot_feeder_phase(df, phase='pu_a', title='Feeder Map', save_path=None):

    fig, ax = plt.subplots(figsize=(12, 9), facecolor='white')

    # Draw all lines
    for b1, b2 in line_segments:
        if b1 in df['bus'].values and b2 in df['bus'].values:
            lat1, lon1 = df.loc[df['bus']==b1, ['x','y']].values[0]
            lat2, lon2 = df.loc[df['bus']==b2, ['x','y']].values[0]
            ax.plot([lon1, lon2], [lat1, lat2],
                    color="#000000", linewidth=1.5, zorder=1)

    voltage_cmap = "Blues"
    vmin, vmax = df[phase].min(), df[phase].max()

    # Separate HV & LV buses
    hv = df[df['kvBase'] > 1.0]
    lv = df[df['kvBase'] <= 1.0]

    # Plot HV buses
    scatter_hv = ax.scatter(
        hv['y'], hv['x'],
        c=hv[phase],
        cmap=voltage_cmap, vmin=vmin, vmax=vmax,
        marker='^', s=85,
        edgecolors='#2c3e50', linewidths=0.8,
        label="12.47 kV Bus",
        alpha=0.95, zorder=3
    )

    # Plot LV buses
    scatter_lv = ax.scatter(
        lv['y'], lv['x'],
        c=lv[phase],
        cmap=voltage_cmap, vmin=vmin, vmax=vmax,
        marker='o', s=70,
        edgecolors='#34495e', linewidths=0.7,
        label="480 V Bus",
        alpha=0.95, zorder=3
    )

    # Overlay PV orange rings 
    if 'has_pv' in df.columns:
        pv_buses = df[df['has_pv'] == True]

        ax.scatter(
            pv_buses['y'], pv_buses['x'],
            s=140,                    # bigger ring
            facecolors='none',
            edgecolors='#ff8c00',
            linewidths=2.2,
            zorder=4                 # above other markers
        )

        pv_legend = mpatches.Circle(
            (0, 0), radius=0.1,
            facecolor='none',
            edgecolor='#ff8c00',
            linewidth=2.2,
            label='Solar PV Bus'
        )

    # Substation marker
    ax.scatter(SUB_LON, SUB_LAT,
               s=250, c='#e74c3c',
               marker='*',
               edgecolors='#c0392b',
               linewidth=1.6,
               label="Substation",
               alpha=0.95, zorder=8)

    # Colorbar
    cbar = plt.colorbar(scatter_hv, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Voltage (per unit)", fontsize=12, weight='semibold', labelpad=10)

    cbar.ax.axhline(0.95, color='#e74c3c', linestyle='--', linewidth=1.5, alpha=0.7)
    cbar.ax.axhline(1.05, color='#e74c3c', linestyle='--', linewidth=1.5, alpha=0.7)

    # Axes + formatting
    ax.set_title(title, fontsize=17, weight='bold', pad=20)
    ax.set_xlabel("Longitude", fontsize=13, weight='semibold')
    ax.set_ylabel("Latitude", fontsize=13, weight='semibold')
    ax.grid(True, linestyle='--', alpha=0.3)

    ax.ticklabel_format(style='plain', useOffset=False)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.3f}'))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, p: f'{y:.3f}'))

    # Feeder bounds
    x_min, x_max = df['y'].min(), df['y'].max()
    y_min, y_max = df['x'].min(), df['x'].max()
    x_pad = (x_max - x_min) * 0.08
    y_pad = (y_max - y_min) * 0.08
    ax.set_xlim(x_min - x_pad, x_max + x_pad)
    ax.set_ylim(y_min - y_pad, y_max + y_pad)
    ax.set_aspect('equal')

    # Legend
    handles, labels = ax.get_legend_handles_labels()

    if 'has_pv' in df.columns:
        handles.append(pv_legend)
        labels.append("Solar PV Bus")

    legend = ax.legend(handles, labels,
                       loc='upper right',
                       frameon=True,
                       framealpha=0.97,
                       edgecolor='#7f8c8d',
                       fontsize=11)

    legend.get_frame().set_facecolor('white')
    plt.tight_layout()

    # Save
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Saved plot to {save_path}")

    plt.show()


# Run plots
plot_feeder_phase(df, 'pu_a',
                  'Distribution Feeder Voltage Map - Phase A',
                  "plots/phase_a.png")
