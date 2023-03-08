### move to home linux
cd 
rm reporter-uninstall.sh
wget https://raw.githubusercontent.com/defi-org-code/ton-access-reporter/master/reporter-uninstall.sh
chmod +x reporter-uninstall.sh
sudo ./reporter-uninstall.sh
echo 'uninstall reporter completed'
rm reporter-install.sh
wget https://raw.githubusercontent.com/defi-org-code/ton-access-reporter/master/reporter-install.sh
chmod +x reporter-install.sh
sudo ./reporter-install.sh 

echo 'install and upgrader reporter completed , run systemctl status reporter'