import streamlit as st
import ee
import geemap.foliumap as geemap
import json

# ------------------------
# 1. EARTH ENGINE INITIALIZATION
# ------------------------
def init_earth_engine(project_id: str):
    """Authenticate and initialize Earth Engine with the given GCP project."""
    ee.Initialize(project=project_id)

# ------------------------
# 2. AREA OF INTEREST
# ------------------------
def get_default_geometry() -> ee.Geometry:
    """Return the default lake boundary polygon (Bellandur Lake sample)."""
    coords = [
        [77.6392446351248, 12.921051012051585],
        [77.63899787189543, 12.920078493132383],
        [77.63889435291664, 12.919004787930328],
        [77.63891849279777, 12.918905443959652],
        [77.63897481918708, 12.918868843539448],
        [77.64090064525978, 12.918105462124162],
        [77.64099720478431, 12.918168205890122],
        [77.64158729076759, 12.918732899074577],
        [77.6439254160206,  12.921726115590571],
        [77.64401392891808, 12.921745722734912],
        [77.64406891420289, 12.92177317273437 ],
        [77.64409573629304, 12.921830687009194],
        [77.64408836311765, 12.921905261527495],
        [77.64500031418271, 12.92281503075012 ],
        [77.64506468719907, 12.92293528735337 ],
        [77.64503786510892, 12.923029401176393],
        [77.64451751656003, 12.923834595767756],
        [77.64441559261746, 12.923892109567786],
        [77.64130959457822, 12.923060772442854],
        [77.64042983002133, 12.923322199510041],
        [77.64032254166074, 12.923311742432603],
        [77.6392446351248,  12.921051012051585]
    ]
    return ee.Geometry.Polygon([coords])


def get_custom_geometry() -> ee.Geometry:
    """Prompt user for a custom GeoJSON polygon and return EE Geometry."""
    st.sidebar.markdown('## AOI Selection')
    choice = st.sidebar.radio('Choose boundary:', ['Default Lake', 'Custom GeoJSON'])
    if choice == 'Custom GeoJSON':
        geojson_str = st.sidebar.text_area(
            'Paste Polygon GeoJSON (Feature or Geometry):', height=200)
        if geojson_str:
            try:
                geojson = json.loads(geojson_str)
                # If Feature, extract geometry
                if 'features' in geojson:
                    geom = geojson['features'][0]['geometry']
                elif 'geometry' in geojson:
                    geom = geojson['geometry']
                else:
                    geom = geojson
                return ee.Geometry(geom)
            except Exception as e:
                st.sidebar.error(f'Invalid GeoJSON: {e}')
                return get_default_geometry()
        else:
            st.sidebar.info('Awaiting GeoJSON input...')
            return get_default_geometry()
    else:
        return get_default_geometry()

# ------------------------
# 3. IMAGE COLLECTION LOADING
# ------------------------
def load_sentinel_collection(aoi: ee.Geometry, start_year: int, end_year: int) -> ee.ImageCollection:
    """Load and filter Sentinel-2 ImageCollection for given years and AOI."""
    start_date = ee.Date.fromYMD(start_year, 1, 1)
    end_date = ee.Date.fromYMD(end_year, 12, 31)
    return (
        ee.ImageCollection('COPERNICUS/S2')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
    )

# ------------------------
# 4. INDEX CALCULATIONS
# ------------------------
def normalize(image: ee.Image) -> ee.Image:
    """Normalize reflectance bands (0-10000) to 0-1."""
    return image.divide(10000)


def add_fai_mci_turbidity(image: ee.Image) -> ee.Image:
    """Compute FAI, MCI, and Turbidity proxies and add as bands."""
    img = normalize(image)
    # FAI
    red, nir, swir = img.select('B4'), img.select('B8'), img.select('B11')
    RED_WL, NIR_WL, SWIR_WL = 665, 842, 1610
    baseline = red.add(swir.subtract(red).multiply(NIR_WL-RED_WL).divide(SWIR_WL-RED_WL))
    fai = nir.subtract(baseline).rename('FAI')
    # MCI
    mci = img.expression(
        'b5 - b4 - (b6 - b4)*((705-665)/(740-665))',
        {'b4': img.select('B4'), 'b5': img.select('B5'), 'b6': img.select('B6')}
    ).rename('MCI')
    # Turbidity
    turb = img.select('B11').divide(img.select('B4')).rename('Turbidity')
    return image.addBands([fai, mci, turb])

# ------------------------
# 5. AGGREGATION & METRICS
# ------------------------
def compute_mean_image(collection: ee.ImageCollection) -> ee.Image:
    """Select index bands and compute mean composite."""
    return collection.select(['FAI', 'MCI', 'Turbidity']).mean()


def compute_mean_value(img: ee.Image, band: str, aoi: ee.Geometry) -> float:
    """Get the mean value of a band over the AOI."""
    return float(
        img.select(band)
           .reduceRegion(
               reducer=ee.Reducer.mean(),
               geometry=aoi,
               scale=10,
               maxPixels=1e9
           )
           .get(band)
           .getInfo()
    )

# ------------------------
# 6. LAYER DISPLAY FUNCTION
# ------------------------
def display_layers(map_obj: geemap.Map, mean_img: ee.Image, layers: list, vis_params: dict, aoi: ee.Geometry):
    """Add specified layers to the map with their visualization parameters."""
    for key in layers:
        map_obj.addLayer(
            mean_img.select(key).clip(aoi),
            vis_params[key],
            f"{key} Index",
            opacity=0.6
        )
    map_obj.addLayer(aoi, {'color':'red'}, 'Boundary')
    map_obj.to_streamlit(height=600)

# ------------------------
# 7. LEGEND DESCRIPTION
# ------------------------
def describe_legends(vis_params: dict, thresholds: dict):
    """Render legend descriptions and threshold info for each index."""
    st.markdown('### 🖼️ Legends & Thresholds')
    for key, params in vis_params.items():
        min_v, max_v = params['min'], params['max']
        palette = ' → '.join(params['palette'])
        th = thresholds.get(key, 'N/A')
        st.markdown(f"**{key}**: Range [{min_v}, {max_v}], Colors: {palette}, Alert if > {th}")

# ------------------------
# 8. UI COMPONENTS
# ------------------------
def render_sidebar_metrics(selected_layers, mean_img, aoi, thresholds):
    st.sidebar.markdown('## 🧪 Water Quality Summary')
    alerts = []
    for key in selected_layers:
        val = compute_mean_value(mean_img, key, aoi)
        st.sidebar.markdown(f'- **{key} Mean:** {val:.3f}')
        if val > thresholds[key]:
            alerts.append(key)
    if alerts:
        st.sidebar.error('⚠️ Alert: ' + ', '.join(alerts) + ' above safe levels!')
    else:
        st.sidebar.success('✅ All metrics within safe limits')

# ------------------------
# 9. MAIN APPLICATION LOGIC
# ------------------------
def main():
    st.title('🌊 LakeHealth Dashboard')
    init_earth_engine('lake-dashboard-464415')
    start_year = st.sidebar.slider('Start Year', 2016, 2024, 2020)
    end_year   = st.sidebar.slider('End Year', start_year, 2024, 2024)
    # AOI choice
    aoi = get_custom_geometry()
    # Layer toggles
    st.sidebar.markdown('## Select Layers')
    layers = ['FAI', 'MCI', 'Turbidity']
    selected = [l for l in layers if st.sidebar.checkbox(l, True)]
    # Load & process imagery
    collection = load_sentinel_collection(aoi, start_year, end_year)
    with_idx = collection.map(add_fai_mci_turbidity)
    mean_img = compute_mean_image(with_idx)
    # Thresholds
    thresholds = {'FAI':0.05, 'MCI':0.02, 'Turbidity':1.8}
    # Render outputs
    render_sidebar_metrics(selected, mean_img, aoi, thresholds)
    vis_params = {
        'FAI':       {'min': -0.1,  'max': 0.1,  'palette': ['white','green','blue']},
        'MCI':       {'min': -0.05, 'max': 0.2,  'palette': ['white','orange','red']},
        'Turbidity': {'min': 0.0,   'max': 3.0,  'palette': ['blue','yellow','red']}
    }
    display_layers(
        geemap.Map(center=[12.922,77.633], zoom=15, google_map='HYBRID'),
        mean_img,
        selected,
        vis_params,
        aoi
    )
    describe_legends(vis_params, thresholds)

if __name__ == '__main__':
    main()
