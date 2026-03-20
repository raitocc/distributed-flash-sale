export default {
    content: [
        "./index.html",
        "./src/**/*.{vue,js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                apple: {
                    bg: '#F5F5F7',
                    card: '#FFFFFF',
                    text: '#1D1D1F',
                    subtext: '#86868B',
                    blue: '#0071E3',
                    red: '#FF3B30'
                }
            },
            fontFamily: {
                sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
            }
        },
    },
    plugins: [],
}
