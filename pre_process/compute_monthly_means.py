"""
Compute monthly means from HEALPix Zarr data

This script computes monthly means for various variables:
- Simple 2D variables: prw, tas, huss, ps, sfcWind (direct monthly mean)
- Derived variables: qsat (saturation deficit - requires tas, huss, ps)
- 3D variables: omega, hur, ta (extracted at specified pressure levels: 850, 500, 300 hPa by default)
- 3D derived: omega from wa (requires wa and ta at pressure levels)

Handles different models (IFS, SCREAM, NICAM, ICON, UM) with varying:
- Dimension names (value/cell, level/lev/pressure)
- Variable names (t/ta, q/hus, w/omega, 2t/tas, sp/ps, 2d/tdas)
- Pressure units (Pa vs hPa)

Author: Laura Paccini
Last updated: October 2025
"""

import os
import json
import datetime
import numpy as np
import xarray as xr
import intake
import easygems.healpix as egh
import sys
import argparse
import time

# =================== Utility Functions =======================

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return np.array([np.datetime64(datetime.datetime(t.year, t.month, t.day, t.hour)) 
                         for t in time_array])
    return time_array

def detect_pressure_units(pressure_coord):
    """
    Detect whether pressure coordinates are in Pascals or hectopascals.
    
    Parameters:
    -----------
    pressure_coord : xarray.DataArray
        Pressure coordinate from dataset
    
    Returns:
    --------
    str : 'Pa' or 'hPa'
    """
    median_pressure = float(np.median(pressure_coord.values))
    
    if median_pressure > 2000:
        units = 'Pa'
        print(f"  Detected pressure units: Pascals (median value: {median_pressure:.1f} Pa)")
    else:
        units = 'hPa'
        print(f"  Detected pressure units: hectopascals (median value: {median_pressure:.1f} hPa)")
    
    sys.stdout.flush()
    return units


def normalize_pressure_levels(pressure_levels_hPa, dataset_pressure_coord):
    """
    Convert user-specified pressure levels (always in hPa) to match dataset units.
    
    Parameters:
    -----------
    pressure_levels_hPa : list
        Pressure levels specified by user in hPa (e.g., [850, 500, 300])
    dataset_pressure_coord : xarray.DataArray
        Pressure coordinate from the dataset
    
    Returns:
    --------
    tuple : (pressure_levels_dataset, units)
        Pressure levels in dataset units and the detected units
    """
    units = detect_pressure_units(dataset_pressure_coord)
    
    if units == 'Pa':
        # Convert from hPa to Pa
        pressure_levels_dataset = [p * 100 for p in pressure_levels_hPa]
        print(f"  Converted pressure levels: {pressure_levels_hPa} hPa → {pressure_levels_dataset} Pa")
    else:
        # Already in hPa
        pressure_levels_dataset = pressure_levels_hPa
        print(f"  Pressure levels: {pressure_levels_hPa} hPa (no conversion needed)")
    
    sys.stdout.flush()
    return pressure_levels_dataset, units


def apply_model_fixes(ds, model_name):
    """
    Apply model-specific fixes for dimension and variable names.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Input dataset
    model_name : str
        Model name (e.g., 'ifs', 'scream', 'nicam')
    
    Returns:
    --------
    xarray.Dataset
        Fixed dataset with standardized names
    """
    print(f"\nApplying fixes for model: {model_name}")
    sys.stdout.flush()
    
    # ===== FIX FOR IFS MODEL =====
    if 'value' in ds.dims and 'cell' in ds.dims:
        print("  Detected IFS model: Applying dimension and variable name fixes...")
        sys.stdout.flush()
        
        # 1. Swap 'value' dimension to 'cell'
        cell_values = ds.coords['cell'].values
        ds = ds.drop_dims('cell')
        ds = ds.rename({'value': 'cell'})
        ds = ds.assign_coords({'cell': cell_values})
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        print("    Swapped 'value' → 'cell' dimension")
        
        # 2. Rename 'level' to 'pressure' if it exists
        if 'level' in ds.dims:
            ds = ds.rename({'level': 'pressure'})
            print("    Renamed 'level' → 'pressure' dimension")
        
        # 3. Rename IFS variable names to standard names
        var_name_mapping = {
            't': 'ta',      # temperature
            'tcwv': 'prw',   # precipitable water vapor
            'w': 'omega',   # vertical velocity (pressure velocity)
            'q': 'hus',     # specific humidity
            'r': 'hur',     # relative humidity
            'u': 'ua',      # zonal wind
            'v': 'va',      # meridional wind
            '2t': 'tas',    # 2m temperature
            '2d': 'tdas',   # 2m dew point temperature
            '10u': 'uas',   # 10m zonal wind
            '10v': 'vas',   # 10m meridional wind
            'slhf': 'hflsd', # surface latent heat flux
            'sshf': 'hflsu', # surface sensible heat flux
            'sp': 'ps',     # surface pressure
            'tcc': 'clt',   # total cloud cover

        }
        
        vars_to_rename = {}
        for old_name, new_name in var_name_mapping.items():
            if old_name in ds.data_vars or old_name in ds.coords:
                vars_to_rename[old_name] = new_name
        
        if vars_to_rename:
            ds = ds.rename(vars_to_rename)
            print(f"    Renamed variables: {vars_to_rename}")
        
        print("  IFS model fixes complete")
        sys.stdout.flush()
    
    # ===== FIX FOR NICAM MODEL =====
    elif 'lev' in ds.dims:
        print("  Detected NICAM model: Renaming 'lev' → 'pressure' dimension...")
        sys.stdout.flush()
        ds = ds.rename({'lev': 'pressure'})
        print("  NICAM model fix complete")
        sys.stdout.flush()
    
    # ===== FIX FOR SCREAM MODEL =====
    elif 'level' in ds.dims:
        print("  Detected SCREAM model: Renaming 'level' → 'pressure' dimension...")
        sys.stdout.flush()
        ds = ds.rename({'level': 'pressure'})
        # SCREAM stores pressure values in 'lev' coordinate
        if 'lev' in ds.coords:
            ds = ds.assign_coords(pressure=('pressure', ds.lev.values))
            ds = ds.drop_vars('lev')
        print("  SCREAM model fix complete")
        sys.stdout.flush()
    
    return ds


def convert_w_to_omega(ds, pressure_levels_hPa):
    """
    Convert vertical velocity (w) to pressure velocity (omega) using ω = -ρgw
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Dataset containing 'wa' (vertical velocity) and 'ta' (temperature)
    pressure_levels_hPa : list
        List of pressure levels in hPa (will be converted to dataset units automatically)
    
    Returns:
    --------
    xarray.DataArray
        Omega variable (pressure velocity in Pa/s)
    """
    print("Converting vertical velocity (wa) to pressure velocity (omega)...")
    sys.stdout.flush()
    
    # Physical constants
    g = 9.81  # gravitational acceleration (m/s²)
    R = 287.04  # specific gas constant for dry air (J/(kg·K))
    
    # Get variables
    w = ds['wa']  # vertical velocity (m/s)
    T = ds['ta']  # temperature (K)
    
    # Normalize pressure levels to dataset units
    pressure_levels_dataset, pressure_units = normalize_pressure_levels(
        pressure_levels_hPa, w.pressure
    )
    
    # Create omega variable for each pressure level
    omega_levels = []
    
    for i, pressure_hPa in enumerate(pressure_levels_hPa):
        pressure_dataset_units = pressure_levels_dataset[i]
        
        # Select data at this pressure level (using dataset units)
        w_level = w.sel(pressure=pressure_dataset_units, method='nearest')
        T_level = T.sel(pressure=pressure_dataset_units, method='nearest')
        
        # Calculate air density: ρ = P / (R * T)
        # Always use pressure in Pascals for the physics calculation
        if pressure_units == 'hPa':
            pressure_Pa = pressure_hPa * 100
        else:
            pressure_Pa = pressure_dataset_units
        
        density = pressure_Pa / (R * T_level)
        
        # Calculate omega: ω = -ρ * g * w
        omega_level = -density * g * w_level
        
        # Add pressure coordinate (use original hPa value for consistency)
        omega_level = omega_level.expand_dims(pressure=[pressure_hPa])
        omega_levels.append(omega_level)
    
    # Concatenate all pressure levels
    omega_combined = xr.concat(omega_levels, dim='pressure')
    
    # Add proper attributes
    omega_combined.attrs = {
        'long_name': 'Pressure velocity (omega)',
        'units': 'Pa/s',
        'description': 'Pressure velocity calculated from vertical velocity using ω = -ρgw',
        'formula': 'omega = -density * 9.81 * vertical_velocity',
        'pressure_levels_hPa': str(pressure_levels_hPa),
        'source_pressure_units': pressure_units
    }
    
    print(f"Omega conversion complete. Pressure levels: {pressure_levels_hPa} hPa")
    sys.stdout.flush()
    
    # Return only the omega variable, not the entire dataset
    return omega_combined

def saturation_vapor_pressure(temperature):
    r"""Calculate the saturation water vapor (partial) pressure.

    Parameters
    ----------
    temperature : array-like
        Air temperature [Kelvin]

    Returns
    -------
    array-like
        Saturation water vapor (partial) pressure

    Notes
    -----
    Taken from MetPy function:
    https://github.com/Unidata/MetPy/blob/34bfda1deaead3fed9070f3a766f7d842373c6d9/src/metpy/calc/thermo.py#L1285

    The formula used is that from [Bolton1980]_ for T in degrees Celsius:

    .. math:: 6.112 e^\frac{17.67T}{T + 243.5}

    """
    # Converted from original in terms of C to use kelvin.
    return 611.2 * np.exp(
        17.67 * (temperature - 273.15) / (temperature - 29.65)
    )

def mixing_ratio(partial_press, total_press, molecular_weight_ratio=0.622):
    r"""Calculate the mixing ratio of a gas.

    This calculates mixing ratio given its partial pressure and the total pressure of
    the air. There are no required units for the input arrays, other than that
    they have the same units.

    Parameters
    ----------
    partial_press : array-like
        Partial pressure of the constituent gas

    total_press : array-like
        Total air pressure

    molecular_weight_ratio : float, optional
        The ratio of the molecular weight of the constituent gas to that assumed
        for air. Defaults to the ratio for water vapor to dry air
        (:math:`\epsilon\approx0.622`).

    Returns
    -------
    array-like
        The (mass) mixing ratio, dimensionless (e.g. Kg/Kg or g/g)

    Notes
    -----
    Taken from MetPy function:
    https://github.com/Unidata/MetPy/blob/34bfda1deaead3fed9070f3a766f7d842373c6d9/src/metpy/calc/thermo.py#L1418

    This function is a straightforward implementation of the equation given in many places,
    such as [Hobbs1977]_ pg.73:

    .. math:: r = \epsilon \frac{e}{p - e}

    .. versionchanged:: 1.0
       Renamed ``part_press``, ``tot_press`` parameters to ``partial_press``, ``total_press``

    """
    return molecular_weight_ratio * partial_press / (total_press - partial_press)

def saturation_mixing_ratio(total_press, temperature):
    r"""Calculate the saturation mixing ratio of water vapor.

    This calculation is given total atmospheric pressure and air temperature.

    Parameters
    ----------
    total_press: array-like
        Total atmospheric pressure [Pa]

    temperature: array-like
        Air temperature [K]

    Returns
    -------
    array-like
        Saturation mixing ratio, dimensionless

    Notes
    -----
    Taken from MetPy function:
    https://github.com/Unidata/MetPy/blob/34bfda1deaead3fed9070f3a766f7d842373c6d9/src/metpy/calc/thermo.py#L1474

    This function is a straightforward implementation of the equation given in many places,
    such as [Hobbs1977]_ pg.73:

    .. math:: r_s = \epsilon \frac{e_s}{p - e_s}

    .. versionchanged:: 1.0
       Renamed ``tot_press`` parameter to ``total_press``

    """
    return mixing_ratio(saturation_vapor_pressure(temperature), total_press)


def clean_attrs_for_netcdf(ds):
    """
    Clean dataset attributes to avoid errors during netCDF output.
    """
    for key in list(ds.attrs):
        val = ds.attrs[key]
        if isinstance(val, dict):
            del ds.attrs[key]
        elif isinstance(val, bool):
            ds.attrs[key] = int(val)
    
    for var in ds.variables:
        for key, val in list(ds[var].attrs.items()):
            if isinstance(val, dict):
                ds[var].attrs[key] = json.dumps(val)
            elif isinstance(val, bool):
                ds[var].attrs[key] = int(val)
    
    return ds


def compute_saturation_deficit(ds):
    """
    Compute saturation deficit (qsat) from temperature, humidity, and pressure.
    
    Handles two cases:
    1. If 'huss' (specific humidity) is available: direct calculation
    2. If 'tdas' (dew point temperature) is available: compute actual humidity from dew point
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Must contain:
        - 'tas' (2m temperature)
        - 'ps' (surface pressure)
        - Either 'huss' (specific humidity) OR 'tdas' (dew point temperature)
    
    Returns:
    --------
    xarray.DataArray
        Saturation deficit in g/kg
    """
    print("  Computing saturation deficit (qsat)...")
    sys.stdout.flush()
    
    # Compute saturation specific humidity
    q2sat_mr = saturation_mixing_ratio(ds['ps'], ds['tas'])
    q2sat = q2sat_mr / (1 + q2sat_mr)
    
    # Determine actual specific humidity
    if 'huss' in ds.data_vars:
        # Case 1: Direct specific humidity available
        print("    Using specific humidity (huss)")
        q_actual = ds['huss']
        formula_str = '1000 * (qsat - huss)'
    elif 'tdas' in ds.data_vars:
        # Case 2: Compute from dew point temperature (IFS case)
        print("    Computing actual humidity from dew point temperature (tdas)")
        q_actual_mr = saturation_mixing_ratio(ds['ps'], ds['tdas'])
        q_actual = q_actual_mr / (1 + q_actual_mr)
        formula_str = '1000 * (qsat - q_from_dewpoint)'
    else:
        raise ValueError("Neither 'huss' nor 'tdas' found in dataset - cannot compute saturation deficit")
    
    # Saturation deficit, convert unit to [g/kg]
    qsat = 1000 * (q2sat - q_actual)
    
    qsat.attrs = {
        'long_name': 'Saturation deficit at 2m',
        'units': 'g/kg',
        'description': 'Difference between saturation specific humidity and actual specific humidity',
        'formula': formula_str
    }
    
    print("  Saturation deficit computed")
    sys.stdout.flush()
    return qsat


def compute_surface_wind_speed(ds):
    """
    Compute surface wind speed (sfcWind) from horizontal wind components.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Must contain 'uas' and 'vas' variables (eastward and northward surface winds)
    
    Returns:
    --------
    xarray.DataArray
        Surface wind speed in m/s
    """
    print("  Computing surface wind speed (sfcWind) from uas and vas...")
    sys.stdout.flush()
    
    # Compute wind speed: sqrt(u^2 + v^2)
    sfcWind = np.sqrt(ds['uas']**2 + ds['vas']**2)
    
    sfcWind.attrs = {
        'long_name': 'Near-Surface Wind Speed',
        'units': 'm s-1',
        'standard_name': 'wind_speed',
        'description': 'Surface wind speed computed from eastward and northward components',
        'formula': 'sqrt(uas^2 + vas^2)'
    }
    
    print("  Surface wind speed computed")
    sys.stdout.flush()
    return sfcWind


def vertical_mass_integration(hus, ps, plev):
    """
    Compute vertical mass integration (Eq.(1) in Chen et al. 2020 EF).
    
    This integrates specific humidity vertically to get precipitable water (prw).
    
    Parameters:
    -----------
    hus : xarray.DataArray
        Specific humidity with vertical coordinate named 'pressure'
    ps : xarray.DataArray
        Surface pressure with same horizontal dimensions as hus
    plev : xarray.DataArray
        Vertical pressure coordinate
    
    Returns:
    --------
    xarray.DataArray
        Vertically integrated water vapor (kg/m^2)
    
    Reference:
    ----------
    Chen et al. (2020) https://doi.org/10.1029/2019EF001435
    """
    print("    Performing vertical mass integration...")
    sys.stdout.flush()
    
    # Ensure pressure is in Pa for calculations
    plev_Pa = plev.copy()
    ps_Pa = ps.copy()
    
    if plev_Pa.max() < 1200:
        plev_Pa = plev_Pa * 100
        print("      Converting pressure coordinate to Pa")
    if ps_Pa.max() < 1200:
        ps_Pa = ps_Pa * 100
    
    # Ensure pressure increases with index (low pressure/top → high pressure/surface)
    if not np.all(np.diff(plev_Pa.values) > 0):
        plev_Pa = plev_Pa[::-1]
        hus = hus.sel(pressure=hus["pressure"][::-1])
    
    # Align coordinates
    plev_Pa = plev_Pa.assign_coords(pressure=plev_Pa)
    hus = hus.assign_coords(pressure=plev_Pa)
    
    # Create 3D fields
    plev_3d = plev_Pa * xr.ones_like(hus)
    ps_3d = ps_Pa * xr.ones_like(hus)
    
    # Mask out levels above surface (where plev > ps)
    hus_masked = hus.where(plev_3d <= ps_3d)
    
    # Compute pressure differences
    dp = np.gradient(plev_Pa.values)
    dp = xr.DataArray(dp, coords={"pressure": plev_Pa}, dims=["pressure"])
    dp_3d = dp * xr.ones_like(hus)
    
    # Integrate: prw = (1/g) * ∫ q dp
    integrand = hus_masked * dp_3d / 9.81
    
    return integrand.sum(dim="pressure")


def compute_precipitable_water(ds):
    """
    Compute precipitable water (prw) from specific humidity profile.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Must contain:
        - 'hus' (specific humidity, 3D with pressure dimension)
        - 'ps' (surface pressure) - if not available, will be estimated from top valid level
    
    Returns:
    --------
    xarray.DataArray
        Precipitable water (integrated water vapor) in kg/m^2
    """
    print("  Computing precipitable water (prw) from specific humidity profile...")
    sys.stdout.flush()
    
    # Get pressure coordinate
    if 'pressure' not in ds['hus'].dims:
        raise ValueError("hus must have a 'pressure' dimension for vertical integration")
    
    plev = ds['hus'].pressure
    hus = ds['hus']
    
    # Get or estimate surface pressure
    if 'ps' not in ds.data_vars:
        print("    ps not found - estimating from lowest valid pressure level")
        
        # Find first valid level from top (assuming pressure goes high to low or low to high)
        mask_valid = ~np.isnan(hus)
        
        # Check pressure direction
        if plev.values[0] < plev.values[-1]:
            # Pressure increases (top to surface) - use argmax
            first_valid_idx = mask_valid.argmax(dim="pressure").compute()
        else:
            # Pressure decreases (surface to top) - reverse, then argmax
            mask_valid_reversed = mask_valid.sel(pressure=mask_valid.pressure[::-1])
            first_valid_idx = mask_valid_reversed.argmax(dim="pressure").compute()
        
        ps = plev.isel(pressure=first_valid_idx)
        print(f"    Estimated ps from pressure level index")
    else:
        ps = ds['ps']
    
    # Perform vertical integration
    prw = vertical_mass_integration(hus, ps, plev)
    
    prw.attrs = {
        'long_name': 'Water Vapor Path',
        'standard_name': 'atmosphere_mass_content_of_water_vapor',
        'units': 'kg m-2',
        'description': 'Vertically integrated water vapor (precipitable water)',
        'formula': '(1/g) * integral(hus * dp)'
    }
    
    print("  Precipitable water computed")
    sys.stdout.flush()
    return prw


def process_variable_monthly(ds, variable, pressure_levels=None):
    """
    Process a variable and compute monthly means.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Input dataset
    variable : str
        Variable name to process
    pressure_levels : list, optional
        Pressure levels in hPa for 3D variables (default: [850, 500, 300])
    
    Returns:
    --------
    xarray.DataArray or xarray.Dataset
        Monthly mean of the variable(s)
    """
    if pressure_levels is None:
        pressure_levels = [850, 500, 300]
    
    print(f"\nProcessing variable: {variable}")
    sys.stdout.flush()
    
    # Special case: saturation deficit (derived variable)
    if variable.lower() in ['qsat', 'q2sd', 'saturation_deficit']:
        # Check for required variables
        required_base = ['tas', 'ps']
        missing_base = [v for v in required_base if v not in ds.data_vars]
        
        # Check if we have either huss or tdas
        has_huss = 'huss' in ds.data_vars
        has_tdas = 'tdas' in ds.data_vars
        
        if missing_base:
            print(f"  ERROR: Missing required base variables for qsat: {missing_base}")
            return None
        
        if not has_huss and not has_tdas:
            print(f"  ERROR: Need either 'huss' (specific humidity) or 'tdas' (dew point) for qsat")
            print(f"  Available variables: {list(ds.data_vars)}")
            return None
        
        # Compute saturation deficit
        qsat = compute_saturation_deficit(ds)
        
        # Compute monthly mean
        print("  Computing monthly mean...")
        sys.stdout.flush()
        qsat_monthly = qsat.resample(time='1ME').mean()
        
        return qsat_monthly.to_dataset(name='qsat')
    
    # Special case: surface wind speed (derived if not present)
    elif variable.lower() == 'sfcwind':
        # Check if sfcWind already exists
        if 'sfcWind' in ds.data_vars:
            print("  sfcWind found in dataset - using directly")
            var_data = ds['sfcWind']
            
            # Compute monthly mean
            print("  Computing monthly mean...")
            sys.stdout.flush()
            var_monthly = var_data.resample(time='1ME').mean()
            
            return var_monthly.to_dataset(name='sfcWind')
        else:
            # Compute from uas and vas
            required_vars = ['uas', 'vas']
            missing = [v for v in required_vars if v not in ds.data_vars]
            if missing:
                print(f"  ERROR: sfcWind not found and missing components: {missing}")
                return None
            
            # Compute surface wind speed
            sfcWind = compute_surface_wind_speed(ds)
            
            # Compute monthly mean
            print("  Computing monthly mean...")
            sys.stdout.flush()
            sfcWind_monthly = sfcWind.resample(time='1ME').mean()
            
            return sfcWind_monthly.to_dataset(name='sfcWind')
    
    # Special case: precipitable water (derived if not present)
    elif variable.lower() == 'prw':
        # Check if prw already exists
        if 'prw' in ds.data_vars:
            print("  prw found in dataset - using directly")
            var_data = ds['prw']
            
            # Compute monthly mean
            print("  Computing monthly mean...")
            sys.stdout.flush()
            var_monthly = var_data.resample(time='1ME').mean()
            
            return var_monthly.to_dataset(name='prw')
        else:
            # Compute from vertical integration of hus
            required_vars = ['hus']
            missing = [v for v in required_vars if v not in ds.data_vars]
            if missing:
                print(f"  ERROR: prw not found and missing required variable: {missing}")
                print(f"  Need 'hus' (3D specific humidity) to compute prw")
                return None
            
            # Check that hus has pressure dimension
            if 'pressure' not in ds['hus'].dims:
                print(f"  ERROR: hus must have a 'pressure' dimension for vertical integration")
                return None
            
            # Compute precipitable water
            prw = compute_precipitable_water(ds)
            
            # Compute monthly mean
            print("  Computing monthly mean...")
            sys.stdout.flush()
            prw_monthly = prw.resample(time='1ME').mean()
            
            return prw_monthly.to_dataset(name='prw')
    
    # Special case: omega from wa (derived variable)
    elif variable == 'omega' and 'wa' in ds.data_vars and 'omega' not in ds.data_vars:
        required_vars = ['wa', 'ta']
        missing = [v for v in required_vars if v not in ds.data_vars]
        if missing:
            print(f"  ERROR: Missing required variables for omega conversion: {missing}")
            return None
        
        # Convert wa to omega at specified pressure levels
        omega = convert_w_to_omega(ds, pressure_levels)
        
        # Compute monthly mean
        print("  Computing monthly mean...")
        sys.stdout.flush()
        omega_monthly = omega.resample(time='1ME').mean()
        
        return omega_monthly.to_dataset(name='omega')
    
    # Standard variable processing
    else:
        if variable not in ds.data_vars:
            print(f"  ERROR: Variable '{variable}' not found in dataset")
            print(f"  Available variables: {list(ds.data_vars)}")
            return None
        
        var_data = ds[variable]
        
        # Check if it's a 3D variable with pressure dimension
        if 'pressure' in var_data.dims:
            print(f"  3D variable detected - extracting at pressure levels: {pressure_levels} hPa")
            sys.stdout.flush()
            
            # Normalize pressure levels to dataset units
            pressure_coord = var_data.pressure
            pressure_levels_dataset, units = normalize_pressure_levels(pressure_levels, pressure_coord)
            
            # Select pressure levels
            var_subset = var_data.sel(pressure=pressure_levels_dataset, method='nearest')
            
            # Compute monthly mean
            print("  Computing monthly mean...")
            sys.stdout.flush()
            var_monthly = var_subset.resample(time='1ME').mean()
            
            # Update pressure coordinate to be in hPa for consistency
            var_monthly = var_monthly.assign_coords(pressure=('pressure', pressure_levels))
            
            return var_monthly.to_dataset(name=variable)
        
        else:
            # 2D variable - simple monthly mean
            print("  2D variable - computing monthly mean...")
            sys.stdout.flush()
            var_monthly = var_data.resample(time='1ME').mean()
            
            return var_monthly.to_dataset(name=variable)


# =================== Main Pipeline =======================

def main():
    parser = argparse.ArgumentParser(
        description='Compute monthly means for various variables from model data.'
    )
    
    # Input/output options
    parser.add_argument('--catalog_url', 
                        default="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml",
                        help='URL of the intake catalog')
    parser.add_argument('--current_location', default="NERSC", 
                        help='Current location in catalog (NERSC or online)')
    parser.add_argument('--catalog_model', default="scream_ne120", 
                        help='Model name in the catalog')
    parser.add_argument('--model_time_freq', default=None,
                        help='Model output time frequency (e.g., "1H", "3H", "6H")')
    parser.add_argument('--catalog_params', default='{"zoom": 8}', 
                        help='JSON string of catalog parameters')
    parser.add_argument('--output_dir', required=True, 
                        help='Output directory for results')
    
    # Variable options
    parser.add_argument('--variables', nargs='+', required=True,
                        help='Variable(s) to process (e.g., prw tas omega qsat)')
    parser.add_argument('--pressure_levels', default='850,500,300',
                        help='Comma-separated pressure levels in hPa for 3D variables (default: 850,500,300)')
    
    # Date filtering
    parser.add_argument('--start_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Parse pressure levels
    pressure_levels = [int(p) for p in args.pressure_levels.split(',')]
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    print("=" * 70)
    print("Monthly Means Computation Script")
    print("=" * 70)
    print(f"Model: {args.catalog_model}")
    print(f"Location: {args.current_location}")
    print(f"Variables: {', '.join(args.variables)}")
    print(f"Pressure levels (for 3D vars): {pressure_levels} hPa")
    print(f"Output directory: {args.output_dir}")
    if args.start_date and args.end_date:
        print(f"Date range: {args.start_date} to {args.end_date}")
    print("=" * 70)
    sys.stdout.flush()
    
    # Load catalog and dataset
    print("\nLoading catalog and dataset...")
    sys.stdout.flush()

    # Parse catalog parameters
    try:
        catalog_params = json.loads(args.catalog_params)
        zoom_level = catalog_params.get('zoom', 'unknown')
    except:
        catalog_params = {'zoom': 8}
        zoom_level = 8
    
    # Open catalog and get dataset
    print(f"Opening catalog from {args.catalog_url}")
    sys.stdout.flush()
    cat = intake.open_catalog(args.catalog_url)[args.current_location]

    print(f"Loading dataset {args.catalog_model}...")
    sys.stdout.flush()

    # Add retry logic for dataset opening (handles intermittent 502 errors for IFS)
    max_retries = 10
    retry_delay = 10  # seconds
    
    for attempt in range(max_retries):
        try:
            ds = cat[args.catalog_model](**catalog_params).to_dask().pipe(
                egh.attach_coords, signed_lon=True
            )
            # Resample IMMEDIATELY for IFS
            if args.catalog_model.startswith('ifs'):
                print(f"Resampling IFS data from hourly to {args.model_time_freq}...")
                ds = ds.resample(time=args.model_time_freq).first()
                print(f"After resampling: {len(ds.time)} time steps")

            print(f"Dataset loaded successfully")
            sys.stdout.flush()
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"WARNING: Failed to load dataset (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Retrying in {retry_delay} seconds...")
                sys.stdout.flush()
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"ERROR: Failed to load dataset after {max_retries} attempts: {e}")
                sys.stdout.flush()
                raise
    
    # Convert time coordinate
    ds['time'] = xr.decode_cf(ds).indexes['time']
    
    print(f"Dataset loaded. Dimensions: {dict(ds.dims)}")
    print(f"Available variables: {list(ds.data_vars)}")
    sys.stdout.flush()
    
    # Apply model-specific fixes
    ds = apply_model_fixes(ds, args.catalog_model)
    
    # Filter by date range if provided
    if args.start_date and args.end_date:
        print(f"\nFiltering data: {args.start_date} to {args.end_date}")
        sys.stdout.flush()
        ds = ds.sel(time=slice(args.start_date, args.end_date))
    
    # Get history attribute
    original_history = ds.attrs.get('history', '')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_history = f"{timestamp}: Monthly means computed by compute_monthly_means.py"
    
    # Process each variable
    print("\n" + "=" * 70)
    print("Processing variables...")
    print("=" * 70)
    sys.stdout.flush()
    
    for variable in args.variables:
        print(f"\n{'=' * 70}")
        print(f"Variable: {variable}")
        print(f"{'=' * 70}")
        
        # Process variable and get monthly means
        result_ds = process_variable_monthly(ds, variable, pressure_levels)
        
        if result_ds is None:
            print(f"Skipping {variable} due to errors")
            continue
        
        # Determine output filename
        var_name = list(result_ds.data_vars)[0]
        
        # Add pressure level info to filename for 3D variables
        if 'pressure' in result_ds[var_name].dims:
            pressure_str = f"_{'_'.join([str(p) for p in pressure_levels])}hPa"
        else:
            pressure_str = ""
        
        # Create filename with model, variable, zoom, and date range
        if args.start_date and args.end_date:
            start_str = args.start_date.replace('-', '')
            end_str = args.end_date.replace('-', '')
            date_str = f"_{start_str}_{end_str}"
        else:
            # Use actual data range
            time_vals = result_ds.time.values
            start_str = str(time_vals[0])[:10].replace('-', '')
            end_str = str(time_vals[-1])[:10].replace('-', '')
            date_str = f"_{start_str}_{end_str}"
        
        out_file = os.path.join(
            args.output_dir,
            f"{args.catalog_model}_monthly_{var_name}{pressure_str}_hp{zoom_level}{date_str}.nc"
        )
        
        # Clean attributes and add metadata
        result_ds = clean_attrs_for_netcdf(result_ds)
        result_ds.attrs.update({
            "history": f"{new_history}; {original_history}",
            "source_model": args.catalog_model,
            "time_resolution": "monthly_mean",
            "healpix_zoom": zoom_level,
            "processing_script": "compute_monthly_means.py",
            "description": f"Monthly means of {var_name}"
        })
        
        if 'pressure' in result_ds[var_name].dims:
            result_ds.attrs['pressure_levels_hPa'] = str(pressure_levels)
        
        # Save to file
        print(f"\nSaving to: {out_file}")
        sys.stdout.flush()
        result_ds.to_netcdf(out_file)
        print(f"✓ Saved successfully")
        sys.stdout.flush()
    
    print("\n" + "=" * 70)
    print("Processing complete!")
    print("=" * 70)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
