import os, sys
import configparser
import fiona
import glob

from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
from rtree import index
import itertools
from collections import OrderedDict

CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(os.path.dirname(__file__), 'script_config.ini'))
BASE_PATH = CONFIG['file_locations']['base_path']

DATA_INTERMEDIATE = os.path.join(BASE_PATH, 'intermediate')
DATA_PROCESSED = os.path.join(BASE_PATH, 'processed')
DATA_FINAL = os.path.join(BASE_PATH, 'final')

def get_files_list(data_directory):

    pathlist = glob.iglob(data_directory + '/*.shp', recursive=True)
    
    # pathlist =[]
    # pathlist.append('data/intermediate/cb.shp')
    # pathlist.append('data/intermediate/cf.shp')

    return pathlist

def remove_vertical_postcodes(path, filename):

    geojson_shapes = []
   
    #Initialze Rtree
    idx = index.Index()
       
    with fiona.open(path, 'r') as source:

        # sink_schema = source.schema.copy()
    
        # Store shapes in Rtree
        for src_shape in source:
            idx.insert(int(src_shape['id']), shape(src_shape['geometry']).bounds, src_shape)           

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
            geojson_shapes.append({
                'type': "Feature",
                'id': p['id'],
                'geometry': p['geometry'],
                'properties': p['properties']
            })

    return geojson_shapes

def generate_sectors(data):
    
    geojson_shapes = []

    # with fiona.open(path, 'r') as source:
    for f in data:
        try:
            postcode_sector = f['properties']['POSTCODE'][:-2]
            geojson_shapes.append({
                'type': "Feature",
                'geometry': f['geometry'],
                'properties': {
                    "postcode": postcode_sector#.replace(" ", "")
                }
            })
        except KeyError:
            print(f)

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

def remove_islands(postcode_sectors, merge=True):

    # Merge MultiPolygons into single Polygon
    removed_islands = []

    for area in postcode_sectors:

        # Avoid intersections
        geom = shape(area['geometry']).buffer(0)
        cascaded_geom = unary_union(geom)

        # Remove islands
        # Add removed islands to a list so that they
        # can be merged in later
        if (isinstance(cascaded_geom, MultiPolygon)):
            for idx, p in enumerate(cascaded_geom):
                if idx == 0:
                    geom = p
                elif p.area > geom.area:
                    removed_islands.append(geom)
                    geom = p
                else:
                    removed_islands.append(p)
        else:
            geom = cascaded_geom

        # Write exterior to file as polygon
        exterior = Polygon(list(geom.exterior.coords))

        # Write to output
        area['geometry'] = mapping(exterior)

        # Add islands that were removed because they were not
        # connected to the main polygon and were not recovered
        # because they were on the edge of the map or inbetween
        # exchanges. Merge to largest intersecting exchange area.
        idx_postcode_sectors = index.Index()
        for idx, postcode_sector in enumerate(postcode_sectors):
            idx_postcode_sectors.insert(idx, shape(postcode_sector['geometry']).bounds, postcode_sector)
        for island in removed_islands:
            intersections = [n for n in idx_postcode_sectors.intersection((island.bounds), objects=True)]

            if len(intersections) > 0:
                for idx, intersection in enumerate(intersections):
                    if idx == 0:
                        merge_with = intersection
                    elif shape(intersection.object['geometry']).intersection(island).length > shape(merge_with.object['geometry']).intersection(island).length:
                        merge_with = intersection

                merged_geom = merge_with.object
                merged_geom['geometry'] = mapping(shape(merged_geom['geometry']).union(island))
                idx_postcode_sectors.delete(merge_with.id, shape(merge_with.object['geometry']).bounds)
                idx_postcode_sectors.insert(merge_with.id, shape(merged_geom['geometry']).bounds, merged_geom)

        postcode_sectors_output = [n.object for n in idx_postcode_sectors.intersection(idx_postcode_sectors.bounds, objects=True)]

    return postcode_sectors_output

def read_in_all_and_write(data_directory):

    my_sectors = []

    pathlist = glob.iglob(data_directory + '/*.shp', recursive=True)

    for path in pathlist:
        with fiona.open(path, 'r') as source:
            for f in source:
                my_sectors.append({
                'type': "Feature",
                'geometry': f['geometry'],
                'properties': f['properties']
                })

    return my_sectors

def write_shapefile(data, directory, filename):

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
    with fiona.open(os.path.join(directory, filename), 'w', driver=sink_driver, crs=sink_crs, schema=sink_schema) as sink:
        [sink.write(feature) for feature in data]

############################
# Run function(s)
############################

list_of_files = get_files_list(DATA_INTERMEDIATE)

for shapefile_path in list_of_files: 
    
    filename = shapefile_path.split("intermediate")[1]
    filename = filename[1:]
    geojson_postcode_sectors = remove_vertical_postcodes(shapefile_path, filename)
    
    print('removed vertical postcodes for {}'.format(filename))
    
    geojson_postcode_sectors = generate_sectors(geojson_postcode_sectors)

    print('generated postcode sectors for {}'.format(filename))

    geojson_postcode_sectors = simplify_shapes(geojson_postcode_sectors)

    print('simplified {}'.format(filename))

    geojson_postcode_sectors = remove_islands(geojson_postcode_sectors)

    print('removed islands for {}'.format(filename))

    write_shapefile(geojson_postcode_sectors, DATA_PROCESSED, filename)

    print('completed {}'.format(filename))


#collect all individual results files
get_final_shapes = read_in_all_and_write(DATA_PROCESSED)

#write to final folder as single file
write_shapefile(get_final_shapes, DATA_FINAL, '_postcode_sectors.shp')
