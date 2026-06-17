#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
install_tmp='/tmp/bt_install.pl'

grep "English" /www/server/panel/config/config.json
if [ "$?" -ne 0 ];then
  public_file=/www/server/panel/install/public.sh
  if [ ! -f $public_file ];then
    cp /www/server/panel/install/public.sh $public_file 2>/dev/null || cp $(dirname $0)/public.sh $public_file 2>/dev/null || true;
  fi
  . $public_file

  download_Url=$NODE_URL
else
  is_English=1
  download_Url=https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main/plugin/mail_sys
fi

echo 'download url...'
echo $download_Url
pluginPath=/www/server/panel/plugin/mail_sys
pluginStaticPath=/www/server/panel/plugin/mail_sys/static


Command_Exists() {
    command -v "$@" >/dev/null 2>&1
}

GetSysInfo() {
    if [ -s "/etc/redhat-release" ]; then
        SYS_VERSION=$(cat /etc/redhat-release)
    elif [ -s "/etc/issue" ]; then
        SYS_VERSION=$(cat /etc/issue)
    fi
    SYS_INFO=$(uname -a)
    SYS_BIT=$(getconf LONG_BIT)
    MEM_TOTAL=$(free -m | grep Mem | awk '{print $2}')
    CPU_INFO=$(getconf _NPROCESSORS_ONLN)

    echo -e ${SYS_VERSION}
    echo -e Bit:${SYS_BIT} Mem:${MEM_TOTAL}M Core:${CPU_INFO}
    echo -e ${SYS_INFO}
    echo -e "Please screenshot above error message and post forum forum.aapanel.com or send email: kern@aapanel.com for help"
}


Replace_symbol(){
# 更换符号为__
    text="${text#"${text%%[![:space:]]*}"}"
    text=${text%% }
    text=${text// /__}
    text=${text//\（/__}
    text=${text//\）/__}
    text=${text//\"/__}
    text=${text//\“/__}
    text=${text//\”/__}
    text=${text//\(/__}
    text=${text//\)/__}
    text=${text//\!/__}
    text=${text//\！/__}
    text=${text//:/__}
    text=${text//：/__}
    text=${text//,/__}
    text=${text//，/__}
    text=${text//。/__}
    text=${text//\$/__}
    text=${text//\{/__}
    text=${text//\}/__}
    text=${text//\[/__}
    text=${text//\]/__}
    text=${text//./__}
    text=${text//-/__}
    text=${text//>/__}
    text=${text//=/__}
    text=${text//\//__}
    text=${text//\'/__}
    
}

Little_tail() {

    arch=$(uname -m)

    if [ -s "/etc/redhat-release" ];then
        SYS_VERSION=$(cat /etc/redhat-release)
    elif Command_Exists hostnamectl; then
        SYS_VERSION=$(hostnamectl | grep "Operating System" | awk -F":" '{print $2}')
    elif [ -s "/etc/issue" ]; then
        SYS_VERSION=$(cat /etc/issue | tr '\n' ' ')
    fi
    
    text="${SYS_VERSION}_${arch}"
    Replace_symbol
    # echo "$text"
    system="$text"
    # echo "$install_status"

    #0-failure, 1-success

}

Red_Error() {
    echo '================================================='
    printf '\033[1;31;40m%b\033[0m\n' "$@"
    GetSysInfo

    if [[ "$@" == "" ]]; then
        url_err_msg="aamail_install_failed"
    else
        text="$@"
        Replace_symbol

        url_err_msg="${text}"
        # echo "url_err_msg: $url_err_msg"
    fi
    install_status="0"
    Little_tail
    # exit 1

}

cpu_arch=$(arch)
if [[ "$cpu_arch" == "x86_64" || "$cpu_arch" == "aarch64" ]]; then
    echo "Supported architecture: $cpu_arch"
else
    if [[ "$is_English" == "1" ]]; then
       echo "Error: Unsupported architecture: $cpu_arch"
    else
       echo "错误: 不支持的架构: $cpu_arch"
    fi
    exit 1
fi

# if [[ $cpu_arch != "x86_64" ]];then
#   echo 'Does not support non-x86 system installation'
#   exit 0
# fi

if [ -f "/usr/bin/apt-get" ];then
  systemver='ubuntu'
elif [ -f "/etc/redhat-release" ];then
  systemver=`cat /etc/redhat-release|sed -r 's/.* ([0-9]+)\..*/\1/'`
  postfixver=`/sbin/postconf mail_version|sed -r 's/.* ([0-9\.]+)$/\1/'`
# else
#   echo 'Unsupported system version'
#   exit 0

fi

Get_Versions() {
    redhat_version_file="/etc/redhat-release"
    deb_version_file="/etc/issue"

    if [[ $(grep "Amazon Linux" /etc/os-release) ]]; then
        os_type="Amazon-"
        os_version=$(cat /etc/os-release | grep "Amazon Linux" | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]+')
        if [[ $os_version == "2023" ]]; then
            os_version="9"
            return
        fi
    fi

    if [[ $(grep TencentOS /etc/os-release) ]]; then
        os_version=$(cat /etc/os-release | grep TencentOS | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]+')
        if [[ $os_version == "2" ]]; then
            os_type="el"
            os_version="7"
        elif [[ $os_version == "3" ]]; then
            os_version="8"
        elif [[ $os_version == "4" ]]; then
            os_type="TencentOS"
            os_version="9"
            # if [[ "$is_English" == "1" ]]; then
            #   echo "TencentOS 4 is not supported, Recommended use CentOS, Rocky, AlmaLinux, Debian, Ubuntu"
            # else
            #   echo "TencentOS 4 不支持，建议使用 CentOS, Rocky, AlmaLinux, Debian, Ubuntu"
            # fi
            # exit 1
        fi
        return
    fi

    if [[ $(grep OpenCloudOS /etc/os-release) ]]; then
        os_type="OpenCloudOS-"
        os_version=$(cat /etc/os-release | grep OpenCloudOS | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]+')
        # if [[ $os_version == "7" ]]; then
        #     os_type="el"
        #     os_version="7"
        # fi
        # if [[ $os_version == "9" ]]; then
        #     if [[ "$is_English" == "1" ]]; then
        #       echo "OpenCloudOS 9 is not supported, Recommended use CentOS, Rocky, AlmaLinux, Debian, Ubuntu"
        #     else
        #       echo "OpenCloudOS 9 不支持，建议使用 CentOS, Rocky, AlmaLinux, Debian, Ubuntu"
        #     fi
        #     exit 1
        # fi
        return
    fi

    if [[ $(grep openEuler /etc/os-release) ]]; then
        os_type="openEuler-"
        os_version=$(cat /etc/os-release | grep openEuler | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]+')
        if [[ "$is_English" == "1" ]]; then
          echo "openEuler is not supported, Recommended use CentOS, Rocky, AlmaLinux, Debian, Ubuntu"
        else
          echo "openEuler 不支持，建议使用 CentOS, Rocky, AlmaLinux, Debian, Ubuntu"
        fi
        exit 1
        
    fi

    if [[ $(grep AlmaLinux /etc/os-release) ]]; then
        os_type="Alma-"
        os_version=$(cat /etc/os-release | grep AlmaLinux | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]+')
        return
    fi

    if [[ $(grep Rocky /etc/os-release) ]]; then
        os_type="Rocky-"
        os_version=$(cat /etc/os-release | grep Rocky | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]+')
        return
    fi

    if [[ $(grep Anolis /etc/os-release) ]] && [[ $(grep VERSION /etc/os-release|grep -Eo '8.8|8.9') ]];then
        if [ -f "/usr/bin/yum" ];then
            os_type="anolis"
            os_version="8"
            return
        fi
    fi        

    if [ -s $redhat_version_file ]; then
        os_type='el'
        if [[ $(grep 'Alibaba Cloud Linux (Aliyun Linux) release 2' $redhat_version_file) ]]; then
            os_version="7"
            return
        fi

        is_aliyunos=$(cat $redhat_version_file | grep Aliyun)
        if [ "$is_aliyunos" != "" ]; then
            return
        fi

        if [[ $(grep "Red Hat" $redhat_version_file) ]]; then
            os_type='el'
            os_version=$(cat $redhat_version_file | grep "Red Hat" | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]')
            return
        fi

        if [[ $(grep "Alibaba Cloud Linux release 3 " /etc/redhat-release) ]]; then
            os_type="ali-linux-"
            os_version="8"
            return
        fi

        if [[ $(grep "Alibaba Cloud" /etc/redhat-release) ]] && [[ $(grep al8 /etc/os-release) ]];then
            os_type="ali-linux-"
            os_version="8"
            return
        fi

        os_version=$(cat $redhat_version_file | grep CentOS | grep -Eo '([0-9]+\.)+[0-9]+' | grep -Eo '^[0-9]')
        if [ "${os_version}" = "5" ]; then
            os_version=""
        fi
        if [ -z "${os_version}" ]; then
            os_version=$(cat /etc/redhat-release | grep Stream | grep -oE "8|9")
        fi
    fi
}

compile_rspamd() {
    # if [[ "$os_type" == "OpenCloudOS-" ]]; then
        dnf install -y git cmake gcc make gcc-c++ ragel lua lua-devel openssl-devel zlib-devel pcre2-devel glib2-devel libevent-devel libicu-devel sqlite-devel json-c-devel hiredis-devel libcurl-devel libarchive libarchive-devel luajit-devel libsodium-devel
    # else
    #     echo "Unsupported system version"
    #     exit 0
    # fi

    wget -O $pluginPath/rspamd-rspamd-3.8.zip $download_Url/install/plugin/mail_sys/rspamd-rspamd-3.8.zip
    unzip $pluginPath/rspamd-rspamd-3.8.zip -d $pluginPath
    cd $pluginPath/rspamd-rspamd-3.8
    mkdir build
    cd build
    cmake ..  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
    make
    make install
    mv ../rspamd.service /lib/systemd/system/rspamd.service
    mkdir -p /etc/rspamd
    cp -r /usr/etc/rspamd/ /etc/rspamd/

    useradd -r -M -s /sbin/nologin _rspamd
    mkdir -p /var/log/rspamd
    chown -R _rspamd:_rspamd /var/log/rspamd
    chmod 755 /var/log/rspamd

    systemctl daemon-reload
    systemctl enable rspamd
    systemctl start rspamd
    make clean
    rm -rf $pluginPath/rspamd-rspamd-3.8/
    compile=1
}

Install_centos7()
{
  if [[ $cpu_arch != "x86_64" ]];then
    echo 'Does not support non-x86 system installation'
    exit 0
  fi

  yum install epel-release -y
  # 卸载系统自带的postfix
  if [[ $cpu_arch = "x86_64" && $postfixver != "3.4.7" ]];then
    yum remove postfix -y
    rm -rf /etc/postfix
  fi
  # 安装postfix和postfix-sqlite
  wget --no-check-certificate -O /tmp/postfix3-3.4.7-1.gf.el7.x86_64.rpm $download_Url/install/plugin/mail_sys/rpm/postfix3-3.4.7-1.gf.el7.x86_64.rpm
  yum localinstall /tmp/postfix3-3.4.7-1.gf.el7.x86_64.rpm -y
  wget --no-check-certificate -O /tmp/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm $download_Url/install/plugin/mail_sys/rpm/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm
  yum localinstall /tmp/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm -y
  # 测试后版本号为3.6.4-1ubuntu1.3
  if [[ ! -f "/usr/sbin/postfix" ]]; then
    yum install postfix -y
    yum install postfix-sqlite -y

    echo '333 Automatically select the version to install postfix and postfix-sqlite' > $install_tmp

  fi
  # 安装dovecot和dovecot-sieve
  yum install dovecot-pigeonhole -y
  if [[ ! -f "/usr/sbin/dovecot" ]]; then
    yum install dovecot -y
  fi

  yum install cyrus-sasl-plain -y
  # 安装pflogsumm 日志分析工具
#  yum install postfix-pflogsumm -y
}


Install_centos8()
{
  yum install epel-release -y
  # 卸载系统自带的postfix
  if [[ $cpu_arch = "x86_64" && $postfixver != "3.4.9" ]];then
    yum remove postfix -y
    rm -rf /etc/postfix
  fi
  # 安装postfix和postfix-sqlite
  wget --no-check-certificate -O /tmp/postfix3-3.4.9-1.gf.el8.x86_64.rpm $download_Url/install/plugin/mail_sys/rpm/postfix3-3.4.9-1.gf.el8.x86_64.rpm
  yum localinstall /tmp/postfix3-3.4.9-1.gf.el8.x86_64.rpm -y
  wget --no-check-certificate -O /tmp/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm $download_Url/install/plugin/mail_sys/rpm/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm
  yum localinstall /tmp/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm -y
  if [[ ! -f "/usr/sbin/postfix" ]]; then
    yum install postfix -y
    yum install postfix-sqlite -y
  fi
  # 安装dovecot和dovecot-sieve
  yum install dovecot-pigeonhole -y
#  wget -O /tmp/dovecot23-2.3.10-1.gf.el8.x86_64.rpm $download_Url/install/plugin/mail_sys/rpm/dovecot23-2.3.10-1.gf.el8.x86_64.rpm
#  yum localinstall /tmp/dovecot23-2.3.10-1.gf.el8.x86_64.rpm -y
  if [[ ! -f "/usr/sbin/dovecot" ]]; then
    yum install dovecot -y
  fi

  yum install cyrus-sasl-plain libsodium libwins -y
  # 安装pflogsumm 日志分析工具
#  yum install postfix-pflogsumm  -y
}

install_rspamd_source()
{
   if [ -s "/usr/bin/apt-get" ];then
      # apt-get install -y lsb-release wget gpg  # for install
      CODENAME=`lsb_release -c -s`
      mkdir -p /etc/apt/keyrings
      wget --no-check-certificate -t 3 -O- https://rspamd.com/apt-stable/gpg.key | gpg --dearmor | tee /etc/apt/keyrings/rspamd.gpg > /dev/null
      echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/rspamd.gpg] http://rspamd.com/apt-stable/ $CODENAME main" | tee /etc/apt/sources.list.d/rspamd.list
      echo "deb-src [arch=amd64 signed-by=/etc/apt/keyrings/rspamd.gpg] http://rspamd.com/apt-stable/ $CODENAME main"  | tee -a /etc/apt/sources.list.d/rspamd.list
      apt-get update -y
      export DEBIAN_FRONTEND=noninteractive
      apt-get --no-install-recommends install rspamd -y --allow-downgrades --allow-remove-essential --allow-change-held-packages
      if [ ! -f "/usr/bin/rspamd" ];then
        echo "official rspamd install failed."
        if [[ "$cpu_arch" == "x86_64" ]]; then
          arch2="amd64"
        elif [[ "$cpu_arch" == "aarch64" ]]; then
          arch2="arm64"
        fi
        wget --no-check-certificate -O rspamd_3.10.2-1~b8a232043~${CODENAME}_${arch2}.deb $download_Url/src/rspamd/rspamd_3.10.2-1~b8a232043~${CODENAME}_${arch2}.deb -t 3
        apt install ./rspamd_3.10.2-1~b8a232043~${CODENAME}_${arch2}.deb -y
        rm -f rspamd_3.10.2-1~b8a232043~${CODENAME}_${arch2}.deb
      fi
    else
      
      # EL_VERSION="$os_version"
      # source /etc/os-release
      # export EL_VERSION=`echo -n $PLATFORM_ID | sed "s/.*el//"`

      if  ([[ "$os_type" == "OpenCloudOS-" ]] || [[ "$os_type" == "TencentOS" ]]) && [[ "$os_version" == "9" ]]; then
          compile_rspamd
      fi

      if [[ "$os_version" != "7" ]] && [[ "$os_version" != "8" ]] && [[ "$os_version" != "9" ]]; then
          if [[ "$is_English" == "1" ]]; then
            echo "This operating system is not supported: ${os_version}"
          else
            echo "不支持的操作系统版本: ${os_version}"
          fi
            hostnamectl
            exit 1
      fi
      wget --no-check-certificate -O /etc/yum.repos.d/rspamd.repo https://rspamd.com/rpm-stable/centos-${os_version}/rspamd.repo -t 3
      yum install rspamd -y
      if [ ! -f "/usr/bin/rspamd" ];then
        if [[ "$os_version" == "8" ]] || [[ "$os_version" == "9" ]]; then
          echo "official rspamd install failed."
          wget --no-check-certificate -O rspamd-3.10.2-1.el${os_version}.${cpu_arch}.rpm $download_Url/src/rspamd/rspamd-3.10.2-1.el${os_version}.${cpu_arch}.rpm -t 3
          yum install rspamd-3.10.2-1.el${os_version}.${cpu_arch}.rpm -y
          rm -f rspamd-3.10.2-1.el${os_version}.${cpu_arch}.rpm
        fi
      fi
    fi

}

install_rspamd()
{
  if [[ $systemver = "7" ]];then
    wget --no-check-certificate -O /etc/yum.repos.d/rspamd.repo https://rspamd.com/rpm-stable/centos-7/rspamd.repo
    rpm --import https://rspamd.com/rpm-stable/gpg.key
    # yum makecache -y
    yum install rspamd -y
  elif [[ $systemver = "8" ]]; then
    wget --no-check-certificate -O /etc/yum.repos.d/rspamd.repo https://rspamd.com/rpm-stable/centos-8/rspamd.repo
    rpm --import https://rspamd.com/rpm-stable/gpg.key
    # yum makecache -y
    yum install rspamd -y
  else
    install_rspamd_source
  fi
}

Install_rspamd_rpm() {
    if [[ $systemver = "7" ]]; then
        wget --no-check-certificate -O rspamd-3.4-1.x86_64.rpm $download_Url/src/rspamd-3.4-1.x86_64.rpm
        rpm -ivh rspamd-3.4-1.x86_64.rpm
        rm -f rspamd-3.4-1.x86_64.rpm
    elif [[ $systemver = "8" ]]; then
        wget --no-check-certificate -O rspamd-3.4-1.x86_64.rpm $download_Url/src/rspamd-3.4-1.x86_64.rpm
        rpm -ivh rspamd-3.4-1.x86_64.rpm
        rm -f rspamd-3.4-1.x86_64.rpm
    else
        install_rspamd_source
    fi
}

Install_ubuntu_debian()
{
  hostname=`hostname`
  # 安装postfix和postfix-sqlite
  debconf-set-selections <<< "postfix postfix/mailname string ${hostname}"
  debconf-set-selections <<< "postfix postfix/main_mailer_type string 'Internet Site'"
  export DEBIAN_FRONTEND=noninteractive
  # apt install postfix -y --allow-downgrades --allow-remove-essential --allow-change-held-packages
  # apt install postfix-sqlite -y --allow-downgrades --allow-remove-essential --allow-change-held-packages
  # apt install sqlite -y --allow-downgrades --allow-remove-essential --allow-change-held-packages
  # # 安装dovecot和dovecot-sieve
  # apt install dovecot-core dovecot-pop3d dovecot-imapd dovecot-lmtpd dovecot-sqlite dovecot-sieve -y --allow-downgrades --allow-remove-essential --allow-change-held-packages
  apt-get update -y
  debPacks="postfix postfix-sqlite sqlite3 libsqlite3-dev dovecot-core dovecot-pop3d dovecot-imapd dovecot-lmtpd dovecot-sqlite dovecot-sieve dovecot-managesieved sasl2-bin libsasl2-modules lsb-release gpg"

  DEBIAN_FRONTEND=noninteractive apt-get install -y $debPacks --allow-downgrades --allow-remove-essential --allow-change-held-packages

  for debPack in ${debPacks}; do
      packCheck=$(dpkg -l ${debPack})
      if [ "$?" -ne "0" ]; then
          DEBIAN_FRONTEND=noninteractive apt-get install -y $debPack --allow-downgrades --allow-remove-essential --allow-change-held-packages
      fi
  done
  # 安装opendkim
#  apt install -y opendkim opendkim-tools
#  wget -O /etc/opendkim.zip $download_Url/install/plugin/mail_sys_en/opendkim.zip -T 10
#  rm -rf /etc/opendkim_old
#  mv /etc/opendkim /etc/opendkim_old
#  unzip -d /etc/ /etc/opendkim.zip
#  chown -R opendkim.opendkim /etc/opendkim

#  wget -O- https://rspamd.com/apt-stable/gpg.key | apt-key add -
#  echo "deb [arch=amd64] http://rspamd.com/apt-stable/ buster main" > /etc/apt/sources.list.d/rspamd.list
#  echo "deb-src [arch=amd64] http://rspamd.com/apt-stable/ buster main" >> /etc/apt/sources.list.d/rspamd.list
#  apt -y update
#  wget http://ftp.br.debian.org/debian/pool/main/i/icu/libicu63_63.2-3_amd64.deb
#  sudo apt install ./libicu63_63.2-3_amd64.deb
#  rm -f ./libicu63_63.2-3_amd64.deb
#  apt install rspamd -y
  # apt install cyrus-sasl-plain libhyperscan5 -y
  # apt install cyrus-sasl-plain -y

  # 安装pflogsumm 日志分析工具
  # apt install pflogsumm -y
}

Install_redis() {
    if [ ! -f /www/server/redis/src/redis-cli ]; then
        wget -O /tmp/redis.sh $download_Url/install/0/redis.sh -T 20
        sed -i "/gen-test-certs/d" /tmp/redis.sh
        bash /tmp/redis.sh install 7.2

        [ ! -f /www/server/redis/src/redis-cli ] && echo 'Redis installation failed' && return

        # 2024/3/15 上午 10:12 如果密码为空，则默认设置redis密码
        REDIS_CONF="/www/server/redis/redis.conf"
        REDIS_PASS=$(cat ${REDIS_CONF} |grep requirepass|grep -v '#'|awk '{print $2}')
        if [ "${REDIS_PASS}" == "" ]; then
            REDIS_PASS=$(cat /dev/urandom | head -n 16 | md5sum | head -c 16)
            echo "# bt mail redis password"
            echo "requirepass ${REDIS_PASS}" >> ${REDIS_CONF}
            /etc/init.d/redis restart
        fi
    fi
}


Install()
{

  if [ ! -d /www/server/panel/plugin/mail_sys ];then
    mkdir -p $pluginPath
    mkdir -p $pluginStaticPath
  fi

  if [ -s "/usr/bin/apt-get" ];then
    Install_ubuntu_debian
  else
    if [[ $systemver = "7" ]]; then
      Install_centos7
    elif [[ $systemver = "8" ]]; then
      Install_centos8
    else 
      # yum install
      yum install epel-release -y
      if [[ "$os_version" == "9" ]] && [ ! -f "/etc/yum.repos.d/epel.repo" ]; then
        wget -O epel-release-9-8.el9.noarch.rpm https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/Packages/e/epel-release-9-8.el9.noarch.rpm -t 3
        yum install epel-release-9-8.el9.noarch.rpm -y
        rm -f epel-release-9-8.el9.noarch.rpm
      fi
      if [[ "$os_type" == "Amazon-" ]] && [[ "$os_version" == "9" ]]; then
        # Amazon Linux 2023
        wget -O hyperscan-5.4.1-2.el9.x86_64.rpm https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/Packages/h/hyperscan-5.4.1-2.el9.x86_64.rpm -t 3
        yum install hyperscan-5.4.1-2.el9.x86_64.rpm -y
        rm -f hyperscan-5.4.1-2.el9.x86_64.rpm
      fi

      yumPacks="postfix postfix-sqlite dovecot dovecot-pigeonhole cyrus-sasl cyrus-sasl-devel cyrus-sasl-plain libsodium jemalloc libwins libicu hyperscan lapack libgfortran libquadmath openblas"
      yum install -y ${yumPacks}
      
      for yumPack in ${yumPacks}; do
          rpmPack=$(rpm -q ${yumPack})
          packCheck=$(echo ${rpmPack} | grep not)
          if [ "${packCheck}" ]; then
              yum install ${yumPack} -y
          fi
      done
    fi
  fi

  # 安装dovecot和dovecot-sieve
  if [ ! -f /etc/dovecot/conf.d/90-sieve.conf ];then
    if [ -f "/usr/bin/apt-get" ];then
      export DEBIAN_FRONTEND=noninteractive
      apt install dovecot-sieve dovecot-managesieved -y
    else
      rm -rf /etc/dovecot_back
      cp -a /etc/dovecot /etc/dovecot_back
      yum remove dovecot -y
      yum install dovecot-pigeonhole -y
      if [ ! -f /usr/sbin/dovecot ]; then
        yum install dovecot -y
      fi
      \cp -a /etc/dovecot_back/* /etc/dovecot
      chown -R vmail:dovecot /etc/dovecot
      chmod -R o-rwx /etc/dovecot

      systemctl enable dovecot
      systemctl restart  dovecot
    fi
  fi

  filesize=`ls -l /etc/dovecot/dh.pem | awk '{print $5}'`
  echo $filesize

  if [ ! -f "/etc/dovecot/dh.pem" ] || [ $filesize -lt 300 ]; then
    openssl dhparam 2048 > /etc/dovecot/dh.pem
  fi

  #获取rspamd网站，检查判断返回是否200
  ping_url=$(curl -I -k -m 10 -o /dev/null -s -w %{http_code}"\n" https://rspamd.com)

  #安装rspamd  如果网络有问题时不使用官方源
  if [ "$ping_url" != "200" ]; then
      Install_rspamd_rpm
  else
      install_rspamd
  fi

  mkdir -p /usr/share/rspamd/www
  wget --no-check-certificate -O /usr/share/rspamd/www/rspamd.zip $download_Url/install/plugin/mail_sys/rspamd.zip -T 20
  cd /usr/share/rspamd/www
  unzip -o rspamd.zip  

  if [ ! -f "/usr/sbin/postfix" ];then
    if [[ "$is_English" == "1" ]]; then
      Red_Error "Error: Fail to install postfix, /usr/sbin/postfix File does not exist"
    fi
    echo "Error: Fail to install postfix, /usr/sbin/postfix File does not exist"
  fi

  if [ ! -f "/usr/sbin/dovecot" ];then
    if [[ "$is_English" == "1" ]]; then
      Red_Error "Error: Fail to install dovecot, /usr/sbin/dovecot File does not exist"
    fi
    echo "Error: Fail to install dovecot, /usr/sbin/dovecot File does not exist"
  fi

  if [ ! -f "/usr/bin/rspamd" ];then
    if [[ "$is_English" == "1" ]]; then
      Red_Error "Error: Fail to install rspamd, /usr/bin/rspamd File does not exist"
    fi
    echo "Error: Fail to install rspamd, /usr/bin/rspamd File does not exist"
  fi

  echo 'Installing script file...' > $install_tmp

  grep "English" /www/server/panel/config/config.json
  if [ "$?" -ne 0 ];then
    wget -O $pluginPath/mail_sys_main.py $download_Url/install/plugin/mail_sys/mail_sys_main.py -T 20
    wget -O $pluginPath/receive_mail.py $download_Url/install/plugin/mail_sys/receive_mail.py -T 20
    wget -O $pluginPath/index.html $download_Url/install/plugin/mail_sys/index.html -T 20
    wget -O $pluginPath/info.json $download_Url/install/plugin/mail_sys/info.json -T 20
    wget -O $pluginPath/icon.png $download_Url/install/plugin/mail_sys/icon.png -T 20
    wget -O $pluginStaticPath/api.zip $download_Url/install/plugin/mail_sys/api.zip -T 20
    wget -O /www/server/panel/BTPanel/static/ckeditor.zip $download_Url/install/plugin/mail_sys/ckeditor.zip -T 20
  else
    
    wget --no-check-certificate -O /tmp/mail_sys.zip  $download_Url/install/plugin/mail_sys_en/mail_sys.zip -T 20

    unzip -o /tmp/mail_sys.zip -d /www/server/panel/plugin/
    rm -f /tmp/mail_sys.zip


    wget -O $pluginStaticPath/api.zip $download_Url/install/plugin/mail_sys_en/api.zip -T 20
    wget -O /www/server/panel/BTPanel/static/ckeditor.zip $download_Url/install/plugin/mail_sys_en/ckeditor.zip -T 20
  fi
  #	#测试用
#  unzip -o /www/server/panel/plugin/mail_sys.zip -d /www/server/panel/plugin/


  if [ ! -d "/www/server/panel/BTPanel/static/ckeditor" ]; then
    unzip /www/server/panel/BTPanel/static/ckeditor.zip -d /www/server/panel/BTPanel/static
  fi
  # 2024/7/26 安装redis
  Install_redis
  echo 'The installation is complete' > $install_tmp
}

#更新
Update()
{
  grep "English" /www/server/panel/config/config.json
  if [ "$?" -ne 0 ];then
    wget -O $pluginPath/mail_sys_main.py $download_Url/install/plugin/mail_sys/mail_sys_main.py -T 20
    wget -O $pluginPath/receive_mail.py $download_Url/install/plugin/mail_sys/receive_mail.py -T 20
    wget -O $pluginPath/index.html $download_Url/install/plugin/mail_sys/index.html -T 20
    wget -O $pluginPath/info.json $download_Url/install/plugin/mail_sys/info.json -T 20
    wget -O $pluginPath/icon.png $download_Url/install/plugin/mail_sys/icon.png -T 20
    wget -O $pluginStaticPath/api.zip $download_Url/install/plugin/mail_sys/api.zip -T 20
    wget -O /www/server/panel/BTPanel/static/ckeditor.zip $download_Url/install/plugin/mail_sys/ckeditor.zip -T 20
  else

    wget --no-check-certificate -O /tmp/mail_sys.zip  $download_Url/install/plugin/mail_sys_en/mail_sys.zip -T 20
    unzip -o /tmp/mail_sys.zip -d /www/server/panel/plugin/
    rm -f /tmp/mail_sys.zip

    wget -O $pluginStaticPath/api.zip $download_Url/install/plugin/mail_sys_en/api.zip -T 20
    wget -O /www/server/panel/BTPanel/static/ckeditor.zip $download_Url/install/plugin/mail_sys_en/ckeditor.zip -T 20
  fi
  if [ -d "/www/server/panel/BTPanel/static/ckeditor" ]; then
    rm -rf /www/server/panel/BTPanel/static/ckeditor
    unzip /www/server/panel/BTPanel/static/ckeditor.zip -d /www/server/panel/BTPanel/static
  fi
}

#卸载
Uninstall()
{
  if [ -s "/usr/bin/apt-get" ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt remove postfix postfix-sqlite -y && rm -rf /etc/postfix
    dpkg -P postfix postfix-sqlite
    apt remove dovecot-core dovecot-imapd dovecot-lmtpd dovecot-pop3d dovecot-sqlite dovecot-sieve dovecot-managesieved -y
    dpkg -P dovecot-core dovecot-imapd dovecot-lmtpd dovecot-pop3d dovecot-sqlite dovecot-sieve dovecot-managesieved
    apt remove opendkim opendkim-tools -y
    dpkg -P opendkim opendkim-tools
    apt remove rspamd -y
    dpkg -P rspamd
  else
    yum remove postfix -y
    yum remove dovecot -y
    yum remove opendkim -y
    yum remove rspamd -y
    yum remove dovecot-pigeonhole -y
  fi

  rm -rf /etc/postfix
  rm -rf /etc/dovecot
  rm -rf /etc/opendkim
  rm -rf /usr/share/rspamd/www
  rm -rf $pluginPath

  # 移动/www/vmail目录到  /www/vmail_日期  目录下
  if [ -d "/www/vmail" ]; then
      current_date=$(date +%Y%m%d_%H%M%S)
      random_number=$RANDOM
      new_dir="/www/vmail_${current_date}_${random_number}"

      if [ -d "$new_dir" ]; then
          echo "Warning: The target directory $new_dir already exists. To avoid data loss, the operation is terminated."
          exit 1
      else
          mv /www/vmail "$new_dir"
          echo "/www/vmail directory successfully moved to $new_dir"
      fi
  fi

}


#操作判断
if [ "${1}" == 'install' ];then
  Get_Versions
  Install
  if [[ "$install_status" != "0" ]] && [[ "$is_English" == "1" ]];then
    install_status="1"
    Little_tail
  fi
  echo '1' > /www/server/panel/data/reload.pl
elif  [ "${1}" == 'update' ];then
  Update
elif [ "${1}" == 'uninstall' ];then
  Uninstall
elif [ "${1}" == 'rspamd' ];then
  Get_Versions
  install_rspamd
fi
