import streamlit as st
import ee
import geemap.foliumap as geemap
import json
import requests

# ------------------------
# 1. EARTH ENGINE INITIALIZATION
# ------------------------
def init_earth_engine(project_id: str):
    """Authenticate and initialize Earth Engine with the given GCP project."""
    ee.Initialize(project=project_id)

# ------------------------
# 2. POLYGON API INTERACTIONS
# ------------------------
API_BASE = 'https://api.agromonitoring.com/agro/1.0'

def list_polygons_api(appid: str) -> list:
    """Fetch list of polygons from AgroMonitoring API."""
    params = {'appid': appid}
    resp = requests.get(f"{API_BASE}/polygons", params=params)
    resp.raise_for_status()
    return resp.json()

# ------------------------
# 3. AREA OF INTEREST SELECTION
# ------------------------

def get_default_geometry() -> ee.Geometry:
    """Return the default lake boundary polygon."""
    coords = [
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
        [77.64406891420289,12.92177317273437 ],
        [77.64409573629304,12.921830687009194],
        [77.64408836311765,12.921905261527495],
        [77.64500031418271,12.92281503075012 ],
        [77.64506468719907,12.92293528735337 ],
        [77.64503786510892,12.923029401176393],
        [77.64451751656003,12.923834595767756],
        [77.64441559261746,12.923892109567786],
        [77.64130959457822,12.923060772442854],
        [77.64042983002133,12.923322199510041],
        [77.64032254166074,12.923311742432603],
        [77.6392446351248,12.921051012051585]
    ]
    return ee.Geometry.Polygon([coords])


def get_polygon_from_api(appid: str) -> ee.Geometry:
    """Let user select an existing polygon from API and return its EE geometry."""
    polygons = list_polygons_api(appid)
    names = [p['name'] + ' (' + p['id'] + ')' for p in polygons]
    choice = st.sidebar.selectbox('Select Saved Polygon', ['--None--'] + names)
    if choice != '--None--':
        idx = names.index(choice)
        geom = polygons[idx]['geo_json']['geometry']
        return ee.Geometry(geom)
    return None


def get_custom_geometry(appid: str) -> ee.Geometry:
    """Prompt user for AOI: default, custom GeoJSON, or saved polygon via API."""
    st.sidebar.markdown('## AOI Selection')
    option = st.sidebar.radio('Boundary Source:', ['Default Lake', 'Custom GeoJSON', 'Saved Polygon'])
    if option == 'Custom GeoJSON':
        geojson_str = st.sidebar.text_area('Paste Polygon GeoJSON:', height=200)
        if geojson_str:
            try:
                gj = json.loads(geojson_str)
                geom = (gj.get('features')[0]['geometry']
                        if 'features' in gj else gj.get('geometry', gj))
                return ee.Geometry(geom)
            except:
                st.sidebar.error('Invalid GeoJSON input.')
                return get_default_geometry()
    elif option == 'Saved Polygon' and appid:
        geom = get_polygon_from_api(appid)
        if geom:
            return geom
        else:
            st.sidebar.info('No saved polygon selected, using default.')
    return get_default_geometry()

# ------------------------
# 4. IMAGE COLLECTION LOADING
# ------------------------
def load_sentinel_collection(aoi: ee.Geometry, sy: int, ey: int) -> ee.ImageCollection:
    start = ee.Date.fromYMD(sy,1,1)
    end   = ee.Date.fromYMD(ey,12,31)
    return (
        ee.ImageCollection('COPERNICUS/S2')
        .filterBounds(aoi)
        .filterDate(start,end)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',10))
    )

# ------------------------
# 5. INDEX CALCULATIONS & AGGREGATION
# ------------------------
def normalize(img: ee.Image) -> ee.Image:
    return img.divide(10000)


def add_fai_mci_turbidity(img: ee.Image) -> ee.Image:
    norm = normalize(img)
    red,nir,swir = norm.select('B4'),norm.select('B8'),norm.select('B11')
    base = red.add(swir.subtract(red).multiply(842-665).divide(1610-665))
    fai = nir.subtract(base).rename('FAI')
    mci = norm.expression('b5-b4-(b6-b4)*((705-665)/(740-665))',
                           {'b4':norm.select('B4'),'b5':norm.select('B5'),'b6':norm.select('B6')}).rename('MCI')
    turb = norm.select('B11').divide(norm.select('B4')).rename('Turbidity')
    return img.addBands([fai,mci,turb])


def compute_mean_image(col: ee.ImageCollection) -> ee.Image:
    return col.select(['FAI','MCI','Turbidity']).mean()


def compute_mean_value(img: ee.Image, band: str, aoi: ee.Geometry) -> float:
    return float(img.select(band).reduceRegion(ee.Reducer.mean(),aoi,10,1e9).get(band).getInfo())

# ------------------------
# 6. DISPLAY & UI
# ------------------------
def display_layers(m, mean_img, layers, vis_params, aoi):
    for k in layers:
        m.addLayer(mean_img.select(k).clip(aoi),vis_params[k],f"{k} Index",opacity=0.6)
    m.addLayer(aoi,{'color':'red'},'Boundary')
    m.to_streamlit(height=600)


def describe_legends(vis_params,thresholds):
    st.markdown('### 🖼️ Legends & Thresholds')
    for k,p in vis_params.items():
        st.markdown(f"**{k}**: Range [{p['min']},{p['max']}], Colors: {'→'.join(p['palette'])}, Alert > {thresholds[k]}")


def render_sidebar_metrics(selected, mean_img, aoi, thresholds):
    st.sidebar.markdown('## 🧪 Water Quality Summary')
    alerts=[]
    for k in selected:
        v=compute_mean_value(mean_img,k,aoi)
        st.sidebar.markdown(f'- **{k} Mean:** {v:.3f}')
        if v>thresholds[k]: alerts.append(k)
    if alerts: st.sidebar.error('⚠️ Alert:'+','.join(alerts)+' above safe levels!')
    else: st.sidebar.success('✅ All metrics within safe limits')

# ------------------------
# 7. MAIN
# ------------------------
def main():
    st.title('🌊 LakeHealth Dashboard')
    init_earth_engine('lake-dashboard-464415')
    appid = st.sidebar.text_input('API Key','',type='password')
    sy = st.sidebar.slider('Start Year',2016,2024,2020)
    ey = st.sidebar.slider('End Year',sy,2024,2024)
    aoi = get_custom_geometry(appid)
    st.sidebar.markdown('## Select Layers')
    layers=['FAI','MCI','Turbidity']
    selected=[l for l in layers if st.sidebar.checkbox(l,True)]
    col=load_sentinel_collection(aoi,sy,ey)
    mean_img=compute_mean_image(col.map(add_fai_mci_turbidity))
    thresh={'FAI':0.05,'MCI':0.02,'Turbidity':1.8}
    render_sidebar_metrics(selected,mean_img,aoi,thresh)
    vis={'FAI':{'min':-0.1,'max':0.1,'palette':['white','green','blue']},
         'MCI':{'min':-0.05,'max':0.2,'palette':['white','orange','red']},
         'Turbidity':{'min':0.0,'max':3.0,'palette':['blue','yellow','red']}}
    display_layers(geemap.Map(center=[12.922,77.633],zoom=15,google_map='HYBRID'),
                   mean_img,selected,vis,aoi)
    describe_legends(vis,thresh)

if __name__=='__main__':
    main()
