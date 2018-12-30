import os, sys
import configparser
import fiona
import glob

from shapely.geometry import shape, MultiPolygon, mapping
from shapely.ops import unary_union
import fiona
import itertools
from collections import OrderedDict

CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(os.path.dirname(__file__), 'script_config.ini'))
BASE_PATH = CONFIG['file_locations']['base_path']

DATA_PROCESSED = os.path.join(BASE_PATH, 'processed')
DATA_FINAL = os.path.join(BASE_PATH, 'final')

def generate_sectors(data_directory):
    
    geojson_shapes = []

    # pathlist = glob.iglob(data_directory + '/*.shp', recursive=True)
    
    pathlist =[]
    pathlist.append('data/processed/cb.shp')
    #pathlist.append('data/processed/cf.shp')

    for path in pathlist:
        with fiona.open(path, 'r') as source:
            for f in source:
                postcode_sector = f['properties']['POSTCODE'][:-2]
                geojson_shapes.append({
                    'type': "Feature",
                    'geometry': f['geometry'],
                    'properties': {
                        "postcode": postcode_sector#.replace(" ", "")
                    }
                })

    postcode_sectors = []

    for key, group in itertools.groupby(geojson_shapes, key=lambda x:x['properties']['postcode']):
        properties, geom = zip(*[(feature['properties'],shape(feature['geometry'])) for feature in group])
        postcode_sectors.append({
            'type': "Feature",
            'geometry': mapping(unary_union(geom)),
            'properties': properties[0]
        })    
            
    return postcode_sectors

def simplify_shapes(data):

    postcode_sectors = []

    for area in data:
        geom = shape(area['geometry'])
        simple_area = geom.simplify(0.99, preserve_topology=False)
        postcode_sectors.append({
            'type': "Feature",
            'geometry': mapping(simple_area),
            'properties': area['properties']
        })            

    return postcode_sectors

def write_shapefile(data, directory, shapefile_filename):

    # Translate props to Fiona sink schema
    prop_schema = []
    for name, value in data[0]['properties'].items():
        fiona_prop_type = next((fiona_type for fiona_type, python_type in fiona.FIELD_TYPES_MAP.items() if python_type == type(value)), None)
        prop_schema.append((name, fiona_prop_type))

    sink_driver = 'ESRI Shapefile'
    sink_crs = {'init': 'epsg:27700'}
    sink_schema = {
        'geometry': data[0]['geometry']['type'],
        'properties': OrderedDict(prop_schema)
    }

    #print(os.path.join(directory, shapefile_filename))
    # Write all elements to output file
    with fiona.open(os.path.join(directory, shapefile_filename), 'w', driver=sink_driver, crs=sink_crs, schema=sink_schema) as sink:
        [sink.write(feature) for feature in data]

geojson_postcode_sectors = generate_sectors(DATA_PROCESSED)

geojson_postcode_sectors = simplify_shapes(geojson_postcode_sectors)

write_shapefile(geojson_postcode_sectors, DATA_FINAL, '_postcode_sectors.shp')

        