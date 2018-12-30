import os, sys
import configparser
import fiona
import glob

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

from rtree import index

CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(os.path.dirname(__file__), 'script_config.ini'))
BASE_PATH = CONFIG['file_locations']['base_path']

DATA_INTERMEDIATE = os.path.join(BASE_PATH, 'intermediate')
DATA_PROCESSED = os.path.join(BASE_PATH, 'processed')
  
def remove_vertical_postcodes(data_directory):

    geojson_shapes = []
    
    pathlist = glob.iglob(data_directory + '/*.shp', recursive=True)
    # pathlist =[]
    # pathlist.append('data/intermediate/cb.shp')
    # pathlist.append('data/intermediate/cf.shp')
    
    #Initialze Rtree
    idx = index.Index()

    for path in pathlist:

        filename = path.split("intermediate/")[1]
        
        with fiona.open(path, 'r') as source:

            sink_schema = source.schema.copy()
        
            # Store shapes in Rtree
            for src_shape in source:
                idx.insert(int(src_shape['id']), shape(src_shape['geometry']).bounds, src_shape)
            
            # Open output file
            with fiona.open(
                    os.path.join(DATA_PROCESSED, filename), 'w',
                    crs=source.crs,
                    driver=source.driver,
                    schema=sink_schema,
                    ) as sink:
        
                print(sink_schema)
        
                # Split list in regular and vertical postcodes
                postcodes = {}
                vertical_postcodes = {}
        
                for x in source:
        
                    if x['properties']['POSTCODE'].startswith('V'):
                        vertical_postcodes[x['id']] = x
                    else:
                        postcodes[x['id']] = x
        
                for key, f in vertical_postcodes.items():
        
                    vpost_geom = shape(f['geometry'])
                    best_neighbour = {'id': 0, 'intersection': 0}
        
                    # Find best neighbour
                    for n in idx.intersection((vpost_geom.bounds), objects=True):
                        if shape(n.object['geometry']).intersection(vpost_geom).length > best_neighbour['intersection'] and n.object['id'] != f['id']:
                            best_neighbour['id'] = n.object['id']
                            best_neighbour['intersection'] = shape(n.object['geometry']).intersection(vpost_geom).length
        
                    # Merge with best neighbour
                    neighbour = postcodes[best_neighbour['id']]
                    merged_geom = unary_union([shape(neighbour['geometry']), vpost_geom])
        
                    merged_postcode = {
                        'id': neighbour['id'],
                        'properties': neighbour['properties'],
                        'geometry': mapping(merged_geom)
                    }
        
                    try:
                        postcodes[merged_postcode['id']] = merged_postcode
                    except:
                        print('print(f)')
                        print(f)
                        print('print(neighbour)')
                        print(neighbour)
                        print('print(merged_postcode)')
                        print(merged_postcode)
                        raise Exception
        
                for key, p in postcodes.items():
                    sink.write(p)
    
    return geojson_shapes

############################
# Run function(s)
############################

remove_vertical_postcodes(DATA_INTERMEDIATE)

