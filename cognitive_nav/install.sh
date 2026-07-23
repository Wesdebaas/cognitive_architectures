# variables for installation
export pkg_dir=~/ros2_ws


cd $pkg_dir/src
git clone -b 4.5.1 --depth 1 https://github.com/mgonzs13/yolo_ros.git $pkg_dir/src/yolo_ros
git clone -b ros2-jazzy https://github.com/Juancams/aws-robomaker-small-house-world.git $pkg_dir/src/aws-robomaker-small-house-world

cd $pkg_dir
python3 -m venv --system-site-packages venv_cogarchs
echo -e '\n# Add venv_cogarchs site-packages to PYTHONPATH\nVENV_SITE_PACKAGES="$VIRTUAL_ENV/lib/python3.12/site-packages"\nif [ -z "$PYTHONPATH" ]; then\n    export PYTHONPATH="$VENV_SITE_PACKAGES"\nelse\n    export PYTHONPATH="$VENV_SITE_PACKAGES:$PYTHONPATH"\nfi' >> venv_cogarchs/bin/activate 

cd venv_cogarchs/
touch COLCON_IGNORE

cd $pkg_dir
source venv_cogarchs/bin/activate

# Install Python dependencies
pip install \
    "numpy<2" \
    "opencv-python-headless>=4.8.1.78" \
    "typing-extensions>=4.4.0" \
    "ultralytics==8.4.6" \
    "lap>=0.5.12" \
    owlready2

# Install dependencies
rosdep install --from-paths src --ignore-src -r -y

# Build workspace
colcon build --symlink-install
source $pkg_dir/install/setup.bash

