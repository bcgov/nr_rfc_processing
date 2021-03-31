import os
import h5py
import logging
import shutil
import click
import datetime
import time
import calendar

import numpy as np
import rasterio as rio

import admin.constants as const

from analysis.support import date_fmt
from process.support import process_by_watershed_or_basin

from multiprocessing import Pool
from osgeo import gdal, gdal_array
from glob import glob
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling

logger = logging.getLogger('snow_mapping')

def build_viirs_tif(date: str, scene: str):
    """
    Build GTiff from raw HDF5 format so the pipeline can 
    use the /data

    Parameters
    ----------
    date : str
        The aquisition date of the granule to be reprojected
        to set up intermediate files in format YYYY.MM.DD
    scene : str
        Raw/HDF5 granule path
    Ref:
        url: https://lpdaac.usgs.gov/resources/e-learning/working-daily-nasa-viirs-surface-reflectance-/data/
    """
    name = ".".join(os.path.split(scene)[-1].split('.')[:-1])
    dest = os.path.join('data/intermediate_tif/viirs', date, f'{name}.tif')
    
    prj = 'PROJCS["unnamed",\
        GEOGCS["Unknown datum based upon the custom spheroid", \
        DATUM["Not specified (based on custom spheroid)", \
        SPHEROID["Custom spheroid",6371007.181,0]], \
        PRIMEM["Greenwich",0],\
        UNIT["degree",0.0174532925199433]],\
        PROJECTION["Sinusoidal"], \
        PARAMETER["longitude_of_center",0], \
        PARAMETER["false_easting",0], \
        PARAMETER["false_northing",0], \
        UNIT["Meter",1]]'
    
    f = h5py.File(scene, 'r')
    fileMetadata = f['HDFEOS INFORMATION']['StructMetadata.0'][()].split() # Read file metadata
    fileMetadata = [m.decode('utf-8') for m in fileMetadata]

    grids = list(f['HDFEOS']['GRIDS']) # List contents of GRIDS directory

    h5_objs = []            # Create empty list
    f.visit(h5_objs.append) # Walk through directory tree, retrieve objects and append to list

    all_datasets = [obj for grid in grids for obj in h5_objs if isinstance(f[obj],h5py.Dataset) and grid in obj] 

    snow = f[[a for a in all_datasets if 'CGF_NDSI_Snow_Cover' in a][0]] # Cloud gap filled
    try: # Due to 2018 viirs missing a fill value: default to documented fillvalue
        fillValue = snow.attrs['_FillValue'][0] # Set fill value to a variable
    except:
        fillValue = 255
    snow = np.array(list(snow))
    ulc = [i for i in fileMetadata if 'UpperLeftPointMtrs' in i][0]    # Search file metadata for the upper left corner of the file
    ulcLon = float(ulc.split('=(')[-1].replace(')', '').split(',')[0]) # Parse metadata string for upper left corner lon value
    ulcLat = float(ulc.split('=(')[-1].replace(')', '').split(',')[1]) # Parse metadata string for upper left corner lat value

    lrc = [i for i in fileMetadata if 'LowerRightMtrs' in i][0]    # Search file metadata for the upper left corner of the file

    yRes, xRes = -375,  375 # Define the x and y resolution   
    geoInfo = (ulcLon, xRes, 0, ulcLat, 0, yRes)        # Define geotransform parameters

    nRow, nCol = snow.shape[0], snow.shape[1]
    driver = gdal.GetDriverByName('GTiff')
    #dataType = gdal_array.NumericTypeCodeToGDALTypeCode(snow.dtype)
    options = ['PROFILE=GeoTIFF']
    outFile = driver.Create(dest, nCol, nRow, 1, options=options)
    band = outFile.GetRasterBand(1)
    band.WriteArray(snow)
    band.FlushCache
    band.SetNoDataValue(float(fillValue))                                                  
    outFile.SetGeoTransform(geoInfo)
    outFile.SetProjection(prj)
    f.close()

def reproject_viirs(date, name, src, dst_crs):
    """Reproject viirs into the target CRS

    Parameters
    ----------
    name : str
        A name string of the granule to be reprojected
        to set up intermediate files
    date : str
        The aquisition date of the granule to be reprojected
        to set up intermediate files in format YYYY.MM.DD
    src : str
        A string path to the granule
    dst_crs : str
        The destination CRS to be reprojected to
    """
    intermediate_tif = os.path.join('data/intermediate_tif/viirs',date,f'{name}_out.tif')
    with rio.open(src, 'r') as src:
        transform, width, height = calculate_default_transform(
                                        src.crs, 
                                        dst_crs, 
                                        src.width, 
                                        src.height, 
                                        src.bounds.left, src.bounds.bottom,
                                        src.bounds.right, src.bounds.top,
                                        resolution=0.006659501656959246
                                    ) 
        kwargs = src.meta.copy()
        kwargs.update({
            'driver': 'GTiff',
            'crs': dst_crs,
            'transform': transform,
            'width': width,
            'height': height
        })
        with rio.open(intermediate_tif, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rio.band(src, i),
                    destination=rio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest
                )

def create_viirs_mosaic(pth: str):
    date = os.path.split(pth)[-1] # Get date var from path
    year = date.split('.')[0]
    int_pth = os.path.join('data','intermediate_tif','viirs',date,'final.tif')
    out_pth = os.path.join('/home/jovyan/geoanalytics_user_shared_data','modis-terra','mosaics','viirs',year)
    try:
        os.makedirs(out_pth)
    except:
        pass
    src_files_path = glob(os.path.join(pth,'*_out.tif'))
    name = os.path.split(pth)[-1]
    src_files_to_mosaic = []
    for f in src_files_path:
        src = rio.open(f, 'r')
        src_files_to_mosaic.append(src)
    if len(src_files_to_mosaic) != 0:
        mosaic, out_trans = merge(
            src_files_to_mosaic, 
            bounds=[-140.977, 46.559, -112.3242, 63.134],
            res=0.006659501656959246
            )
        out_meta = src.meta.copy()
        out_meta.update({
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                      })
        with rio.open(int_pth, "w", **out_meta) as dst:
            dst.write(mosaic)
        for f in src_files_to_mosaic:
            f.close()
    fin_pth = os.path.join(out_pth,f'{date}.tif')

def distribute(func, args):
    # Multiprocessing support to manage Pool scope
    with Pool(6) as p:
        p.starmap(func, args)
        
def clean(date):
    residual_files = glob(os.path.join('data','intermediate_tif','modis',date,'*.tif'))
    if len(residual_files) != 0:
        print('Cleaning up residual files...')
        for f in residual_files:
            os.remove(f)

            
def process_viirs(date: str):
    """
    Main trigger for processing modis from HDF5 -> GTiff and 
    then clipping to watersheds/basins

    Parameters
    ----------
    date : str
        The target date to process granules into mosaic
        and into watershed/basin GTiffs
    """
    try:
        os.makedirs(os.path.join('data','intermediate_tif','viirs',date))
    except:
        pass 


    print('VIIRS Process Started')
    bc_alberes = 'EPSG:3153'
    dst_crs = 'EPSG:4326'
    intermediate_pth = os.path.join('data','intermediate_tif','viirs', date)
    try:
        os.makedirs(intermediate_pth)
    except:
        pass
    viirs_granules = glob(os.path.join('/home/jovyan/geoanalytics_user_shared_data','modis-terra', 'VNP10A1F.001', date, '*.h5'))    

    print('BUILDING INITIAL TIFS FROM HDF5')
    proc_inputs = []
    for i in range(len(viirs_granules)): 
        proc_inputs.append((date, viirs_granules[i]))
    distribute(build_viirs_tif, proc_inputs)

    print('REPROJECTING TIFFS')
    intermediate_tifs = glob(os.path.join(intermediate_pth, '*.tif'))

    reproj_args = []
    for tif in intermediate_tifs:
        name = ".".join(os.path.split(tif)[-1].split('.')[:-1])
        reproj_args.append((date, name, tif, dst_crs))
    distribute(reproject_viirs, reproj_args)

    print('CREATING DAILY MOSAIC')
    create_viirs_mosaic(intermediate_pth)
    