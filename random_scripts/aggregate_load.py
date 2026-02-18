"""
Get the hourly load profile across the entire district. Save in in this folder.
"""

import pandas as pd

load_data_path = "raw_data/load_timeseries_data.csv"
load_data_df = pd.read_csv(load_data_path)

load_data_df['hour_index'] = load_data_df.iloc[:, 0] // 4 + 1
hourly_loads = load_data_df.groupby('hour_index').mean().reset_index()

# get the total load for each hour by summing across all load columns
hourly_loads["Load (kW)"] = hourly_loads.iloc[:, 1:].sum(axis=1)
hourly_loads["Hour"] = range(1, len(hourly_loads) + 1)

hourly_loads = hourly_loads[["Hour", "Load (kW)"]]

hourly_loads.to_csv("random_scripts/hourly_load_profile.csv", index=False)
