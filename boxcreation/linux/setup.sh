############################################
# AdareVM linux apt setup
############################################

# install python3.10
sudo apt update
sudo apt install python3.10
# make sure calling python3 will call python3.10
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
# install pip via python3.10
python3 -m ensurepip

# install poetry
curl -sSL https://install.python-poetry.org | python3 -