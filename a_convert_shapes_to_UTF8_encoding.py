import os, sys
import configparser
import glob

from osgeo import ogr

CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(os.path.dirname(__file__), 'script_config.ini'))
BASE_PATH = CONFIG['file_locations']['base_path']

DATA_RAW_SHAPES = os.path.join(BASE_PATH, 'raw', 'codepoint-poly_2743371')
DATA_INTERMEDIATE = os.path.join(BASE_PATH, 'intermediate')

def convert_to_correct_encoding(data_directory, field_name_target):

    driver = ogr.GetDriverByName("ESRI Shapefile")

    pathlist = glob.iglob(data_directory + '/**/*.shp', recursive=True)
    
    for path in pathlist:
        
        filename = path.split("letter_pc_code/")[1]

        # Get the input Layer
        inShapefile = path
        inDriver = ogr.GetDriverByName("ESRI Shapefile")
        inDataSource = inDriver.Open(inShapefile, 0)
        inLayer = inDataSource.GetLayer()
        #inLayer.SetAttributeFilter("POSTCODE = 'POSTCODE'")

        # Create the output LayerS
        outShapefile = os.path.join(DATA_INTERMEDIATE, filename)
        outDriver = ogr.GetDriverByName("ESRI Shapefile")

        # Remove output shapefile if it already exists
        if os.path.exists(outShapefile):
            outDriver.DeleteDataSource(outShapefile)

        # Create the output shapefile
        outDataSource = outDriver.CreateDataSource(outShapefile)
        out_lyr_name = os.path.splitext( os.path.split( outShapefile )[1] )[0]
        outLayer = outDataSource.CreateLayer( out_lyr_name, geom_type=ogr.wkbMultiPolygon )
        
        # Add input Layer Fields to the output Layer if it is the one we want
        inLayerDefn = inLayer.GetLayerDefn()
        for i in range(0, inLayerDefn.GetFieldCount()):
            fieldDefn = inLayerDefn.GetFieldDefn(i)
            fieldName = fieldDefn.GetName()
            outLayer.CreateField(fieldDefn)

        # Get the output Layer's Feature Definition
        outLayerDefn = outLayer.GetLayerDefn()
        
        # Add features to the ouput Layer
        for inFeature in inLayer:
            # Create output Feature
            outFeature = ogr.Feature(outLayerDefn)

            # Add field values from input Layer
            for i in range(0, outLayerDefn.GetFieldCount()):
                fieldDefn = outLayerDefn.GetFieldDefn(i)
                fieldName = fieldDefn.GetName()

                outFeature.SetField(outLayerDefn.GetFieldDefn(i).GetNameRef(),
                    inFeature.GetField(i))

            # Set geometry as centroid
            geom = inFeature.GetGeometryRef()
            outFeature.SetGeometry(geom.Clone())
            # Add new feature to output Layer
            outLayer.CreateFeature(outFeature)
            outFeature = None

        # Save and close DataSources
        inDataSource = None
        outDataSource = None  
            
convert_to_correct_encoding(DATA_RAW_SHAPES, 'POSTCODE')
