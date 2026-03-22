import { google } from 'googleapis';

export async function getProperties() {
  try {
    const privateKey = process.env.GOOGLE_PRIVATE_KEY
      ?.trim()
      ?.replace(/^["']|["']$/g, '') // Remove potential wrapping quotes
      ?.replace(/\\n/g, '\n');

    const auth = new google.auth.GoogleAuth({
      credentials: {
        client_email: process.env.GOOGLE_CLIENT_EMAIL,
        private_key: privateKey,
      },
      scopes: ['https://www.googleapis.com/auth/spreadsheets.readonly'],
    });

    const sheets = google.sheets({ version: 'v4', auth });
    const response = await sheets.spreadsheets.values.get({
      spreadsheetId: process.env.GOOGLE_SHEET_ID,
      range: 'Sheet1!A2:I', // Match admin_app's columns: A:Date, B:Title, C:Region, D:Rooms, E:Price, F:Poster, G:Desc, H:Views, I:Featured
    });

    const rows = response.data.values;
    if (!rows || rows.length === 0) {
      return [];
    }

    return rows.map((row, index) => ({
      id: index + 2, // Row index in sheet
      date: row[0],
      title: row[1],
      region: row[2],
      rooms: row[3],
      price: parseInt(row[4], 10) || 0,
      posterUrl: row[5],
      description: row[6],
      views: parseInt(row[7], 10) || 0,
      isFeatured: row[8] === '1',
    }));
  } catch (error) {
    console.error('Error fetching properties:', error);
    return [];
  }
}

export async function getPropertyById(id: string) {
  const properties = await getProperties();
  return properties.find((p) => p.id.toString() === id);
}
