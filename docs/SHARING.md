# Data Sharing
There are many ways how to share MyTraL data among different physical computers.
This is just a few examples for the inspiration.


## Custom MyTraL Data Location
MyTraL stores data to the following directories by **default**:

* **Linux**:
    - `/home/user/.local/share/mytral`

You can reconfigure the path to data (or even have multiple locations) with `MYTRAL_DATA_DIR` environment variable:

* **Linux**:

```
export MYTRAL_DATA_DIR=/my/custom/directory/with/mytral/data
```


## Shared Drive
The simplest way how to share MyTraL data is shared cloud drive like Google Drive.

Method:

* **Step 1**: Create a shared drive account.
* **Step 2**: Configure your system to have a directory which is synced to shared cloud drive:
    * Linux: `/home/user/insync`
* **Step 3**: Copy your existing data to the shared directory:
    * Linux: `cp -rvf /home/user/.local/share/mytral /home/user/insync/mytral`
* **Step 4**: Configure MyTraL to use data on the shared drive:
    * Linux (`~/.zshrc` or `~/.bashrc` or your shell rc file):
      `export MYTRAL_DATA_DIR="/home/user/insync/mytral"`

**Final hint**: make sure to regularly backup your data - do not trust MyTraL and/or share drive vendor.


## Git LFS
If you want to have history of changes and like Git and its workflow, then you can use Git LFS (Large File Storage).

Git LFS stores MyTraL JSON files as normal text, but replaces photos, recordings and Parquet files with tiny pointer files inside Git, pushing the actual heavy binaries to a separate storage cloud.

Providers (consider size of your data, mine is ~3GB):

* **GitLab**
    * Free tier includes 5GB of storage per project (which includes LFS).
* **GitHub**
    * Free tier includes 1GB of Git LFS storage. Paid data plan ~$5/month for 50GB.
* **Codeberg**
    * Regular storage 750MB, with LFS up to 1.5GB, then approval (non-profit host).


### Git LFS Configuration
Method:

* **Step 1**: Install Git LFS extension:
    * Linux (Ubuntu/Debian):
        * `sudo apt-get install git-lfs`
    * Mac (via Homebrew):
        * `brew install git-lfs`
    * Windows (via Winget):
        * `winget install github.git-lfs`
* **Step 2**: Initialize your system:
    * `git lfs install`
* **Step 3**: Create your new Git repository:
    * Go to GitLab/GitHub/* and create new (private) repository - ideally named `mytral`.
* **Step 4**: Migrate existing MyTraL repository or start over with new:
    * If you already use MyTraL and want migrate existing repository:
        * MyTraL stores its data by default to:
            * Linux: `/home/user/.local/share/mytral`
        * Rename the `mytral` directory to backup the content.
        * Clone new Git repository to your local machine and `mytral` folder:
            * `git clone https://gitlab.com/your-username/mytral.git`
        * Copy the content of original `mytral` directory from backup to the Git repo you cloned.
        * **Do NOT add and push your files yet!**
* **Step 4**: Tell Git LFS which files to track:
    * Run the following commands inside your Git repository folder so that Git creates `.gitattributes` file with the LFS configuration:

```
# track recordings
git lfs track "*.gpx"
git lfs track "*.tcx"
git lfs track "*.fit"

# track photos (add any other extensions you have, like .png or .jpeg)
git lfs track "*.jpg"
git lfs track "*.png"

# track normalized Parquet files
git lfs track "*.parquet"
```

* **Step 5**: Push Git LFS configuration:

```
git add .gitattributes
git commit -m "chore: initialize git lfs tracking BLOBs"
```

* **Step 6**: Push your data:
    * Now its time to add your data and push them to Git - they will be handled by Git LFS.


