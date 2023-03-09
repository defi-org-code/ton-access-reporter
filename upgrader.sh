### move to home linux
cd 
rm access-reporter-uninstall.sh
wget https://raw.githubusercontent.com/defi-org-code/ton-access-reporter/master/access-reporter-uninstall.sh
chmod +x access-reporter-uninstall.sh
sudo ./access-reporter-uninstall.sh
echo 'uninstall reporter completed'
rm access-reporter-install.sh
wget https://raw.githubusercontent.com/defi-org-code/ton-access-reporter/master/access-reporter-install.sh
chmod +x access-reporter-install.sh
sudo ./access-reporter-install.sh 

echo 'install and upgrader reporter completed , run systemctl status reporter'