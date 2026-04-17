# Database Usage Guide

## In-Memory Database (Default)

When you load an SDF file, the data is stored in an **in-memory SQLite database**. This database:
- Exists only while the application is running
- Is automatically created when you load an SDF file
- Contains 4 tables: compounds, metadata, mass_spectrum, mol_data
- Is lost when you close the application

## Persistent Database (Optional)

To save data to a file that persists after closing the application:

### Step 1: Enable Persistent Database
- Check the checkbox labeled "Save database to file:" in the Load SDF File section

### Step 2: Choose Database Location
- Click the "Choose Location…" button (only enabled when checkbox is checked)
- Select where to save the database file (e.g., C:\my_data\compounds.db)
- The filename will display in the label (e.g., "compounds.db")

### Step 3: Load SDF File
- Click "Browse…" to select your SDF file
- Click "Load" to load the compounds

### Result
The database file is created with all data from the SDF file. You can:
- Open it again later (it will persist)
- Open it with external SQLite tools
- Back it up for safekeeping

## Database Location

By default, the persistent database is saved in the location you choose. 

### Common Locations:
- Windows: C:\Users\[YourUsername]\Documents\
- You can choose any location on your computer

## Database Structure

The SQLite database contains 4 tables:

### 1. compounds
- Stores main compound data (name, formula, MW, CAS number, IUPAC name, SMILES, InChI)
- Has indexes on: name, formula, cas_number

### 2. metadata
- Stores all other SDF fields not in compounds table
- Linked to compounds by compound_id

### 3. mass_spectrum
- Stores mass spectrum peak data (m/z, intensity, base peak)
- Linked to compounds by compound_id
- Has indexes on: compound_id, mz

### 4. mol_data
- Stores references to RDKit molecule objects (kept in memory)
- Linked to compounds by compound_id

## Example Usage

1. Open the EI Fragment Calculator
2. Check "Save database to file:"
3. Click "Choose Location…" and select: C:\data\my_compounds.db
4. Click "Browse…" and select your SDF file
5. Click "Load"
6. Data is now saved to C:\data\my_compounds.db
7. Close the application
8. Next time you start: your data is still in C:\data\my_compounds.db

## Querying the Database Externally

You can query the database using any SQLite tool:

```sql
-- View all compounds
SELECT * FROM compounds;

-- View metadata for a compound
SELECT field_name, field_value FROM metadata 
WHERE compound_id = 1;

-- View mass spectrum peaks
SELECT mz, intensity FROM mass_spectrum 
WHERE compound_id = 1 ORDER BY mz;

-- Search by name
SELECT * FROM compounds WHERE name LIKE '%caffeine%';
```
