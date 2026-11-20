#!/usr/bin/env python
# coding: utf-8

# # Data Pipelines for Spatial Quasi-Experiments with Dewey Data
# 
# Sean McCulloch, 11 October 2026
# 
# This notebook processes geographic microdata from Dewey Data into an analysis dataset for a simple spatial DiD.
# 
# **Outline**
# 
# 0. Clean and append together ATTOM house transaction data from Dewey; load in two polluting plant locations
# 1. Go to a projected CRS and draw circles around the 2 polluting plants
# 2. Spatial join housing sales to polluting plant circles
# 3. Calculate houses' distances to the plant
# 4. Aggregate joined sales to rings with average prices in the pre vs. post period

# ## Setup

# In[1]:


import geopandas as gpd 
import pandas as pd
import numpy as np
import glob 
import os

# Paths are relative to this notebook (src/pgm/), so the code runs wherever the repo is saved
filepath = "../../"
src = filepath + "src/"
bld = filepath + "bld/"


# ## 0. Clean and append together ATTOM house transaction data from Dewey
# 
# ### a) Deed transfers (recorder data)
# 
# List out all the files in the data extract from Dewey and append the individual CSVs into one combined dataframe.

# In[2]:


attom_dir = src + "raw/recorder/"
files = sorted(glob.glob(os.path.join(attom_dir, "*.csv.gz")))
print(f"Found {len(files)} files")

sales = pd.concat(
    (pd.read_csv(f, dtype={"PROPERTYUSESTANDARDIZED": str}, parse_dates=["RECORDINGDATE"])
     for f in files),
    ignore_index=True)

# Drop sales with missing data
# TRANSACTIONTYPE is empty in this extract
sales = sales.drop(columns="TRANSACTIONTYPE")

# 999999999 is ATTOM's placeholder for an unmatched property
sales["ATTOMID"] = sales["ATTOMID"].astype("Int64")
sales.loc[sales["ATTOMID"] == 999999999, "ATTOMID"] = pd.NA
sales


# #### Sample selection
# 
# Restrict to detached single-family houses and arm's-length transactions, with sale prices above $10,000 and below $10 million.

# In[3]:


# Detached single family house 
sales = sales[sales['PROPERTYUSESTANDARDIZED'] == "385"]
# Arms length
sales = sales[sales['ARMSLENGTHFLAG'] == 1]
# Sale price restrictions 
sales = sales[sales['TRANSFERAMOUNT'] >= 10000]
sales = sales[sales['TRANSFERAMOUNT'] <= 10000000]


# #### Sale price in real dollars
# 
# Deflate with CPI-U (all items), monthly, averaged to annual. Real prices are in 2025 dollars.

# In[4]:


sales["sale_year"] = sales["RECORDINGDATE"].dt.year

# CPI-U (all items), monthly, averaged to annual
url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
cpi = pd.read_csv(url, index_col=0, parse_dates=True).iloc[:, 0]
cpi_yr = cpi.groupby(cpi.index.year).mean()

# Real prices in 2025 dollars
base = cpi_yr[2025]
sales["sale_price_real"] = sales["TRANSFERAMOUNT"] * base / sales["sale_year"].map(cpi_yr)


# In[5]:


os.makedirs(bld, exist_ok=True)
sales.to_csv(bld + "attom_sales.csv", index=False)
print(sales.shape)


# In[6]:


sales


# ### b) Tax assessor data
# 
# Also process ATTOM tax assessor data, because there are no coordinates in the deed data. We can match across datasets using the ID provided by ATTOM (`ATTOMID`).

# In[7]:


# List files
assessor_dir = src + "raw/assessor/"
files = sorted(glob.glob(os.path.join(assessor_dir, "*.parquet")))
print(f"Found {len(files)} files")

# Combine csvs into one dataframe
parcels = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
parcels["ATTOMID"] = pd.to_numeric(parcels["ATTOMID"]).astype("Int64")


# Drop missing or bad geocodes (zeros, -1, points far outside Rhode Island).

# In[8]:


in_ri = (parcels["LONGITUDE"].between(-71.92, -71.10) &
         parcels["LATITUDE"].between(41.10, 42.03))
print(f"Dropping {(~in_ri).sum()} parcels with missing or out-of-state coordinates")
parcels = parcels[in_ri].reset_index(drop=True)

assert parcels["ATTOMID"].is_unique
parcels.to_parquet(bld + "attom_parcels.parquet", index=False)


# Attach coordinates to each sale by merging on `ATTOMID`.

# In[9]:


sales_coordinates = sales.merge(parcels, on="ATTOMID", how="inner", validate="m:1")

sales_coordinates.to_parquet(bld + "attom_sales_geo.parquet", index=False)
print(parcels.shape, sales.shape, sales_coordinates.shape)
sales_coordinates


# ### c) Load the two plant locations
# 
# Similar column names across the two geodatasets can get confusing, so rename columns.

# In[10]:


plants_df = pd.read_csv(src + "raw/tri2005RIlist.csv")

plants_df['plantid'] = plants_df.index + 1

renamecoords = {'lon':'plant_lon', 'lat':'plant_lat', 'year':'plant_year'}

plants_df = plants_df.rename(columns=renamecoords)


# Thus far, everything is standard tabular data cleaning. Now, start geospatial operations.

# ## 1. Set up geodataframes, go to a projected CRS and draw circles around the 2 polluting plants
# 
# ### a) Convert regular dataframes to geodataframes

# In[11]:


# Sales
sales_coordinates_gdf = gpd.GeoDataFrame(
    sales_coordinates,
    geometry=gpd.points_from_xy(sales_coordinates["LONGITUDE"], sales_coordinates["LATITUDE"]),
    crs="EPSG:4326",   # lat/lon in degrees (WGS84)
)

# Plants
plants_gdf = gpd.GeoDataFrame(
    plants_df,
    geometry=gpd.points_from_xy(plants_df["plant_lon"], plants_df["plant_lat"]),
    crs="EPSG:4326",   # lat/lon in degrees (WGS84)
)

plants_gdf.to_file(bld + "plant_points.json", driver='GeoJSON')


# ### b) Convert to a projected coordinate reference system (CRS) to get distances in meters

# In[12]:


sales_coordinates_gdf = sales_coordinates_gdf.to_crs(epsg=5070)
plants_gdf = plants_gdf.to_crs(epsg=5070)


# ### c) Draw 2 km radius circles around the plants

# In[13]:


plants_gdf.geometry = plants_gdf.geometry.buffer(2000)
plants_gdf


# In[14]:


# Save files for illustration before the spatial join 
sales_coordinates_gdf.to_crs(epsg=4326).to_file(bld + "sales_gdf.json", driver='GeoJSON')
plants_gdf.to_crs(epsg=4326).to_file(bld + "plant_circles.json", driver='GeoJSON')


# ## 2. Spatial join housing sales to polluting plants' circles
# 
# The default `sjoin` gives an inner spatial join; see the documentation for more options.

# In[15]:


sales_in_rings = sales_coordinates_gdf.sjoin(plants_gdf)
sales_in_rings


# In[16]:


sales_in_rings


# In[17]:


sales_in_rings.to_crs(epsg=4326).to_file(bld + "sales_in_rings.json", driver="GeoJSON")


# ## 3. Calculate distance to the plant
# 
# Get each sale's associated plant point as a GeoSeries, then measure the distance from the house to the plant.

# In[18]:


plant_pts = gpd.GeoSeries(
    gpd.points_from_xy(sales_in_rings["plant_lon"], sales_in_rings["plant_lat"]),
    index=sales_in_rings.index,
    crs="EPSG:4326",            # plant coordinates are lat/lon convert to projected CRS again
).to_crs(sales_in_rings.crs)             

plant_pts


# In[19]:


sales_in_rings["distance_to_plant"] = sales_in_rings.geometry.distance(plant_pts)
sales_in_rings


# In[20]:


sales_in_rings.to_crs(epsg=4326).to_file(bld + "sales_in_rings.json", driver="GeoJSON")


# Looks correct on a map.

# ## 4. Aggregate joined sales to rings with average prices in the pre vs. post period
# 
# Remember, the standard DiD takes differences using 4 averages: Treat Pre, Treat Post, Control Pre, Control Post.
# 
# $$\hat\delta = (\bar{p}_{\text{Treat, Post}} - \bar{p}_{\text{Treat, Pre}}) - (\bar{p}_{\text{Control, Post}} - \bar{p}_{\text{Control, Pre}})$$
# 
# Make binary indicators: treatment (within 1 km of the plant) vs. control (1–2 km), and pre vs. post. Sales in 2005, the year the plants appear, are dropped.

# In[21]:


# Make binary indicators
# Treatment vs Control
sales_in_rings["treatment"] = (sales_in_rings["distance_to_plant"] < 1000).astype(int)

# Pre vs. Post 

sales_in_rings = sales_in_rings[sales_in_rings['sale_year'] != 2005]
sales_in_rings["post"] = (sales_in_rings["sale_year"] > sales_in_rings["plant_year"]).astype(int)

sales_in_rings["treatment"], sales_in_rings["post"] 


# In[22]:


sales_in_rings.RECORDINGDATE


# In[23]:


sales_in_rings


# In[24]:


# Get averages for the DiD 
avg = (sales_in_rings.groupby(["treatment", "post"])["sale_price_real"]
            .agg(["mean", "sem", "count"])
            .unstack("post"))
print(avg.round(0))

print(312847.0 - 298624.0 - (313488.0 - 291066.0))
print(np.sqrt(3038.0**2 + 3649.0**2 + 13738.0**2 + 6701.0**2))


# The DiD indicates an $8,200 depreciation in value, or about 1–2%. However, standard errors are large, so it is not significant.
# 
# There is a lot more spread in house prices for the treatment group than the control group. Why?

# We can also get averages in the 4 treatment groups by plant for the 2 plants, giving 8 means.

# In[25]:


avg = (sales_in_rings.groupby(["plantid", "treatment", "post"])["sale_price_real"]
            .agg(["mean", "sem", "count"])
            .unstack("post"))
print(avg.round(0))


# In[26]:


# Plant 1: (Treat post - treat pre) - (control post - control pre)
print(285924.0 - 262485.0 - (289572.0 - 268047.0))

# Plant 2: (Treat post - treat pre) - (control post - control pre)
print(408831.0 - 385802.0 - (408548.0 - 375220.0))


# Moderately large effect in plant 2, approximately no effect in plant 1, though again, caveat that we have low precision.
