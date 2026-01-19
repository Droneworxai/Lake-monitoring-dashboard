import streamlit as st
import ee
import geemap.foliumap as geemap
import folium

# Initialize Earth Engine
ee.Initialize(project='lake-dashboard-464415')

# Sidebar title
st.sidebar.title("LakeHealth Dashboard")
start_year = st.sidebar.slider("Start Year", 2016, 2024, 2020)
end_year = st.sidebar.slider("End Year", start_year, 2024, 2024)

# Define the lake geometry
lake = ee.Geometry.Polygon([[  # Bellandur Lake sample
    [77.6392446351248,12.921051012051585],
    [77.63899787189543,12.920078493132383],
    [77.63889435291664,12.919004787930328],
    [77.63891849279777,12.918905443959652],
    [77.63897481918708,12.918868843539448],
    [77.64090064525978,12.918105462124162],
    [77.64099720478431,12.918168205890122],
    [77.64158729076759,12.918732899074577],
    [77.6439254160206,12.921726115590571],
    [77.64401392891808,12.921745722734912],
    [77.64406891420289,12.92177317273437],
    [77.64409573629304,12.921830687009194],
    [77.64408836311765,12.921905261527495],
    [77.64500031418271,12.92281503075012],
    [77.64506468719907,12.92293528735337],
    [77.64503786510892,12.923029401176393],
    [77.64451751656003,12.923834595767756],
    [77.64441559261746,12.923892109567786],
    [77.64130959457822,12.923060772442854],
    [77.64042983002133,12.923322199510041],
    [77.64032254166074,12.923311742432603],
    [77.6392446351248,12.921051012051585]
]])

# Load Sentinel-2 image collection
collection = ee.ImageCollection('COPERNICUS/S2') \
    .filterBounds(lake) \
    .filterDate(f"{start_year}-01-01", f"{end_year}-12-31") \
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))

# Compute FAI and MCI
def add_fai_mci(image):
    red = image.select('B4')
    nir = image.select('B8')
    swir1 = image.select('B11')

    # Constants for band wavelengths
    RED_WL = 665
    NIR_WL = 842
    SWIR_WL = 1610

    baseline = red.add(
        swir1.subtract(red).multiply(NIR_WL - RED_WL).divide(SWIR_WL - RED_WL))
    fai = nir.subtract(baseline).rename('FAI')

    mci = image.expression(
        'b5 - b4 - (b6 - b4) * ((705 - 665)/(740 - 665))',
        {
            'b4': image.select('B4'),
            'b5': image.select('B5'),
            'b6': image.select('B6')
        }).rename('MCI')

    return image.addBands(fai).addBands(mci)

# Apply and compute mean of both indices
with_indices = collection.map(add_fai_mci)
mean_image = with_indices.select(['FAI', 'MCI']).mean()

# Reduce region mean value
fai_mean = mean_image.select('FAI').reduceRegion(
    ee.Reducer.mean(), lake, scale=10, maxPixels=1e9).get('FAI')

mci_mean = mean_image.select('MCI').reduceRegion(
    ee.Reducer.mean(), lake, scale=10, maxPixels=1e9).get('MCI')

# Visual parameters
fai_vis = {'min': -0.1, 'max': 0.1, 'palette': ['white', 'green', 'blue']}
mci_vis = {'min': -0.05, 'max': 0.2, 'palette': ['white', 'orange', 'red']}

# Create dual map layout
Map = geemap.Map(center=[12.922, 77.633], zoom=15, google_map='HYBRID')
Map.addLayer(mean_image.select('FAI'), fai_vis, 'FAI Algae Index', opacity=0.6)
Map.addLayer(mean_image.select('MCI'), mci_vis, 'MCI Algae Index', opacity=0.6)
Map.addLayer(lake, {'color': 'red'}, 'Lake Boundary')
Map.to_streamlit(height=550)

# Display legends
st.markdown("### 🖼️ Algae Index Color Legends")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**FAI Scale:** ⬜ White → 🟩 Green → 🔵 Blue")
    st.markdown("*Floating Algae Index*")
with col2:
    st.markdown("**MCI Scale:** ⬜ White → 🟧 Orange → 🔴 Red")
    st.markdown("*Maximum Chlorophyll Index*")

# Show individual mean values
fai_val = fai_mean.getInfo()
mci_val = mci_mean.getInfo()
st.subheader("📊 Algal Bloom Detection")
st.markdown(f"**FAI Mean:** {fai_val:.4f}")
st.markdown(f"**MCI Mean:** {mci_val:.4f}")

# Provide health alert
threshold_fai = 0.05
threshold_mci = 0.02

if fai_val > threshold_fai or mci_val > threshold_mci:
    st.markdown("### 🚨 Alert: Algae Bloom Detected")
    if fai_val > threshold_fai:
        st.markdown(f"- **FAI** is above safe level: {fai_val:.4f} > {threshold_fai}")
    if mci_val > threshold_mci:
        st.markdown(f"- **MCI** is above safe level: {mci_val:.4f} > {threshold_mci}")
else:
    st.success("✅ Water quality appears within safe limits based on FAI and MCI.")
# Ready for next step: turbidity, algal bloom detection, and alerts

# # Time Series Chart of NDWI
# st.subheader(f"Lake Health Indices for {year}")

# ndwi_series = with_indices.select('NDWI') \
#     .map(lambda img: img.set({
#         'date': img.date().format(),
#         'mean': img.reduceRegion(
#             reducer=ee.Reducer.mean(),
#             geometry=lake,
#             scale=10,
#             maxPixels=1e9
#         ).get('NDWI')
#     }))
    
# ndwi_dates = ndwi_series.aggregate_array('date').getInfo()
# ndwi_values = ndwi_series.aggregate_array('mean').getInfo()

# ndvi_series = with_indices.select('NDVI') \
#     .map(lambda img: img.set({
#         'date': img.date().format(),
#         'mean': img.reduceRegion(
#             reducer=ee.Reducer.mean(),
#             geometry=lake,
#             scale=10,
#             maxPixels=1e9
#         ).get('NDVI')
#     }))

# ndvi_dates = ndvi_series.aggregate_array('date').getInfo()
# ndvi_values = ndvi_series.aggregate_array('mean').getInfo()

# # 🖼 Show both NDWI and NDVI charts side-by-side
# # st.subheader(f"Lake Health Indices for {year}")
# col1, col2 = st.columns(2)

# with col1:
#     st.markdown("### NDWI Time Series")
#     fig1, ax1 = plt.subplots(figsize=(5, 3))
#     ax1.plot(ndwi_dates, ndwi_values, marker='o', color='blue')
#     ax1.set_title('NDWI over Time')
#     ax1.set_xlabel('Date')
#     ax1.set_ylabel('NDWI')
#     ax1.grid(True)
#     plt.xticks(rotation=45)
#     st.pyplot(fig1)

# with col2:
#     st.markdown("### NDVI Time Series")
#     fig2, ax2 = plt.subplots(figsize=(5, 3))
#     ax2.plot(ndvi_dates, ndvi_values, marker='o', color='green')
#     ax2.set_title('NDVI over Time')
#     ax2.set_xlabel('Date')
#     ax2.set_ylabel('NDVI')
#     ax2.grid(True)
#     plt.xticks(rotation=45)
#     st.pyplot(fig2)

# # ✅ Full Updated LakeHealth Dashboard with MNDWI Change Detection
# import streamlit as st
# import ee
# import geemap.foliumap as geemap
# import datetime
# import matplotlib.pyplot as plt

# # Initialize Earth Engine
# ee.Initialize(project='lake-dashboard-460621')

# # Streamlit Sidebar - Year Selection
# st.sidebar.title("LakeHealth Dashboard")
# start_year = st.sidebar.slider("Start Year", 2016, 2024, 2016)
# end_year = st.sidebar.slider("End Year", start_year, 2024, 2022)

# # Define AOI - Lake Polygon (21 vertices)
# lake = ee.Geometry.Polygon([[
#     [77.6392446351248,12.921051012051585],
#     [77.63899787189543,12.920078493132383],
#     [77.63889435291664,12.919004787930328],
#     [77.63891849279777,12.918905443959652],
#     [77.63897481918708,12.918868843539448],
#     [77.64090064525978,12.918105462124162],
#     [77.64099720478431,12.918168205890122],
#     [77.64158729076759,12.918732899074577],
#     [77.6439254160206,12.921726115590571],
#     [77.64401392891808,12.921745722734912],
#     [77.64406891420289,12.92177317273437],
#     [77.64409573629304,12.921830687009194],
#     [77.64408836311765,12.921905261527495],
#     [77.64500031418271,12.92281503075012],
#     [77.64506468719907,12.92293528735337],
#     [77.64503786510892,12.923029401176393],
#     [77.64451751656003,12.923834595767756],
#     [77.64441559261746,12.923892109567786],
#     [77.64130959457822,12.923060772442854],
#     [77.64042983002133,12.923322199510041],
#     [77.64032254166074,12.923311742432603],
#     [77.6392446351248,12.921051012051585]  # Close the polygon
# ]])

# # Load Sentinel-2 Data for Both Years
# def load_composite(year):
#     start = f"{year}-01-01"
#     end = f"{year}-06-15"
#     col = ee.ImageCollection('COPERNICUS/S2') \
#         .filterBounds(lake) \
#         .filterDate(start, end) \
#         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))

#     def add_indices(image):
#         ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
#         ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
#         mndwi = image.normalizedDifference(['B3', 'B11']).rename('MNDWI')
#         return image.addBands([ndwi, ndvi, mndwi]) \
#                 .select(['B3', 'B4', 'B8', 'B11', 'NDWI', 'NDVI', 'MNDWI'])

#     return col.map(add_indices).mean()

# start_img = load_composite(start_year)
# end_img = load_composite(end_year)

# # Calculate MNDWI Difference
# mndwi_diff = end_img.select('MNDWI').subtract(start_img.select('MNDWI')).rename('MNDWI_Diff')

# # Classify Water Gain/Loss (threshold = +/- 0.1)
# water_gain = mndwi_diff.gt(0.1)
# water_loss = mndwi_diff.lt(-0.1)

# # Estimate Area Gain/Loss
# area_gain = water_gain.multiply(ee.Image.pixelArea()).reduceRegion(
#     reducer=ee.Reducer.sum(),
#     geometry=lake,
#     scale=10,
#     maxPixels=1e9
# ).get('MNDWI_Diff')

# area_loss = water_loss.multiply(ee.Image.pixelArea()).reduceRegion(
#     reducer=ee.Reducer.sum(),
#     geometry=lake,
#     scale=10,
#     maxPixels=1e9
# ).get('MNDWI_Diff')

# # Show Area Info
# st.sidebar.markdown("---")
# st.sidebar.markdown(f"### 📉 Water Loss: **{ee.Number(area_loss).divide(1e4).format('%.2f').getInfo()} ha**")
# st.sidebar.markdown(f"### 📈 Water Gain: **{ee.Number(area_gain).divide(1e4).format('%.2f').getInfo()} ha**")

# # Visualize Water Change Map
# st.subheader("🔍 Water Loss/Gain Areas")
# MapDiff = geemap.Map(center=[12.922, 77.633], zoom=15)

# mndwi_diff_vis = {
#     'min': -0.5, 'max': 0.5,
#     'palette': ['red', 'white', 'blue']  # Red = loss, Blue = gain
# }

# MapDiff.addLayer(mndwi_diff, mndwi_diff_vis, 'MNDWI Difference')
# MapDiff.addLayer(lake, {'color': 'black'}, 'Original Lake Boundary')
# MapDiff.to_streamlit(height=500)

# st.markdown("Legend: **Red = Water Loss**, **Blue = Water Gain**")
