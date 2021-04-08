node('zavijava_rfc') {
    // ENVS to be set for this job
    //    * ENS_NETWORK_DRIVE
    //    * ENS_DRIVEMAPPING
    //    * RFC_ARTIFACTS_FOLDER
    //
    stage('checkout') {
        //sh 'if [ ! -d "$TEMP" ]; then mkdir $TEMP; fi'
        checkout([$class: 'GitSCM', branches: [[name: '$TAGNAME']], extensions: [], userRemoteConfigs: [[url: 'https://github.com/bcgov/nr-rfc-processing']]])    
    }
    stage('configure drive mappings') {
    bat '''
        if NOT EXIST %RFC_DRIVEMAPPING%:\\nul  (
            net use %RFC_DRIVEMAPPING%: %RFC_NETWORK_DRIVE% /PERSISTENT:NO
            @REM powershell -File ./mapdrives.ps1
        )

        IF NOT EXIST %RFC_ARTIFACTS_FOLDER% (
            echo creating the folder %RFC_ARTIFACTS_FOLDER% 
            mkdir %RFC_ARTIFACTS_FOLDER%
        )

        IF NOT EXIST %RFC_OBJ_STORE_DRIVEMAPPING%:\\nul (
            echo creating the folder %RFC_ARTIFACTS_FOLDER% 
            net use %RFC_OBJ_STORE_DRIVEMAPPING%: %RFC_OBJ_STOR_UNC% /PERSISTENT:NO
        )

        echo complete

        :: print the network mappings
        net use
        '''
    }
    // combine the build of ens and snowpack
    // configure the job so it can not be run concurrently multiple times
    stage('conda env setup') {
        // if check existence of a miniconda directory, if not then install
        // https://dev.to/waylonwalker/installing-miniconda-on-linux-from-the-command-line-4ad7

        // create a conda env directory on fileshare
        // install conda env
        //  conda env create --file environment.yaml --prefix $CONDAENVPATH
        bat '''
        SET CONDABIN=%RFC_ARTIFACTS_FOLDER%\\miniconda\\condabin
        SET condaEnvPath=%RFC_ARTIFACTS_FOLDER%\\rfc_conda_envs\\nr-rfc-processing
        SET condaEnvFilePath=%WORKSPACE%\\environment.yaml
        SET condaEnvFilePath=%condaEnvFilePath:/=\\%
        SET CONDABIN=%CONDABIN:/=\\%
        SET PATH=%CONDABIN%;%PATH%

        if NOT EXIST %condaEnvPath% (
            %CONDABIN%\\conda.bat env create --prefix %condaEnvPath% --file %condaEnvFilePath%
        )
        call conda.bat activate %condaEnvPath%
        call conda.bat env update --file environment.yaml
        pip install -r requirements.txt
        pip install -e .
        conda.bat deactivate
        '''
    }
    withCredentials([file(credentialsId: 'SNOWPACK_ENVS_FILE', variable: 'SNOWPACK_ENVS_PTH')]) {
        stage('run snowpack analysis') {
            bat '''
                SET CONDABIN=%RFC_ARTIFACTS_FOLDER%\\miniconda\\condabin
                SET condaEnvPath=%RFC_ARTIFACTS_FOLDER%\\rfc_conda_envs\\nr-rfc-processing
                SET NORM_ROOT=%RFC_OBJ_STORE_DRIVEMAPPING%:\\norm
                SET PATH=%CONDABIN%;%PATH%

                call conda.bat activate %condaEnvPath%
                

                ::pip install -r .\\requirements.txt

                :: ----------------------------------------------
                :: SNOWPACK_ENVS_PTH
                echo env var param is: %SNOWPACK_ENVS_PTH%
                echo SNOWPACK_SECRETS: %SNOWPACK_SECRETS%

                %condaEnvPath%\\python run.py daily-pipeline --envpth=%SNOWPACK_ENVS_PTH% --date 2021.03.15
            '''
        }
    }
}
