<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloud CRM & Document Manager</title>
    <!-- Memuat Tailwind CSS langsung dari CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 text-gray-800 font-sans antialiased">

    <!-- ==========================================
         BAGIAN 1: LAYAR LOGIN PIN
         ========================================== -->
    <div id="login-view" class="min-h-screen flex items-center justify-center px-4">
        <div class="bg-white p-8 rounded-xl shadow-lg w-full max-w-md text-center border border-gray-200">
            <div class="mb-6">
                <span class="text-4xl">🔒</span>
                <h2 class="text-2xl font-bold mt-4 text-gray-900">Akses CRM</h2>
                <p class="text-gray-500 text-sm mt-1">Masukkan PIN untuk masuk ke sistem</p>
            </div>
            
            <input type="password" id="pin-input" 
                class="w-full border-2 border-gray-300 p-3 rounded-lg mb-4 text-center text-xl tracking-[0.5em] focus:border-blue-500 focus:outline-none transition-colors" 
                placeholder="••••••">
            
            <button onclick="handleLogin()" 
                class="w-full bg-blue-600 text-white p-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors shadow-md">
                Buka Dashboard
            </button>
            
            <p id="login-error" class="text-red-500 text-sm mt-4 hidden">PIN yang Anda masukkan salah.</p>
        </div>
    </div>

    <!-- ==========================================
         BAGIAN 2: DASHBOARD UTAMA (Awalnya Disembunyikan)
         ========================================== -->
    <div id="dashboard-view" class="hidden min-h-screen flex-col">
        
        <!-- Header / Navigasi -->
        <header class="bg-blue-800 text-white p-4 shadow-md sticky top-0 z-10">
            <div class="max-w-7xl mx-auto flex justify-between items-center">
                <div class="flex items-center gap-2">
                    <span class="text-2xl">📁</span>
                    <h1 class="text-xl font-bold tracking-wide">Inla CRM</h1>
                </div>
                <button onclick="handleLogout()" 
                    class="bg-blue-700 hover:bg-red-500 text-sm px-4 py-2 rounded-lg font-medium transition-colors">
                    Keluar
                </button>
            </div>
        </header>

        <!-- Area Konten Utama -->
        <main class="flex-1 p-4 md:p-8 max-w-7xl mx-auto w-full">
            
            <!-- Area Pencarian & Tombol Tambah -->
            <div class="flex flex-col md:flex-row gap-4 mb-6 justify-between">
                <input type="text" id="search-input" 
                    placeholder="Cari perusahaan, nama PIC, atau dokumen..." 
                    class="flex-1 border border-gray-300 p-3 rounded-lg shadow-sm focus:border-blue-500 focus:outline-none">
                
                <button class="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg font-semibold shadow-sm transition-colors flex items-center justify-center gap-2">
                    <span>+</span> Tambah Customer Baru
                </button>
            </div>

            <!-- Tabel Data Customer -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
                <table class="w-full text-left border-collapse min-w-[800px]">
                    <thead>
                        <tr class="bg-gray-50 border-b border-gray-200 text-gray-600 text-sm uppercase">
                            <th class="p-4 font-semibold">Perusahaan</th>
                            <th class="p-4 font-semibold">PIC / Kontak</th>
                            <th class="p-4 font-semibold">Status</th>
                            <th class="p-4 font-semibold text-center">Dokumen</th>
                            <th class="p-4 font-semibold text-right">Aksi</th>
                        </tr>
                    </thead>
                    <tbody id="customer-table-body" class="divide-y divide-gray-200">
                        <!-- Contoh Baris Data (Akan diisi dinamis oleh JavaScript nanti) -->
                        <tr class="hover:bg-blue-50 cursor-pointer transition-colors group">
                            <td class="p-4">
                                <div class="font-bold text-gray-900">PT Inovasi Langit</div>
                                <div class="text-sm text-gray-500">Jakarta Selatan</div>
                            </td>
                            <td class="p-4">
                                <div class="font-medium">Budi Santoso</div>
                                <div class="text-sm text-gray-500">0812-3456-7890</div>
                            </td>
                            <td class="p-4">
                                <span class="bg-green-100 text-green-800 text-xs font-bold px-2 py-1 rounded-full">Aktif</span>
                            </td>
                            <td class="p-4 text-center">
                                <span class="bg-gray-100 text-gray-700 text-xs font-bold px-2 py-1 rounded">3 File</span>
                            </td>
                            <td class="p-4 text-right">
                                <button class="text-blue-600 hover:text-blue-800 font-medium text-sm">Lihat Detail</button>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

        </main>
    </div>

    <!-- Script Logika UI Dasar -->
    <script>
        // Logika sederhana untuk berpindah dari layar login ke dashboard
        function handleLogin() {
            const pin = document.getElementById('pin-input').value;
            // Nanti kita akan tambahkan logika validasi ke backend Vercel di sini
            if (pin.length > 3) { // Validasi sementara
                // Simpan PIN di memori sementara browser untuk digunakan sebagai header API nanti
                sessionStorage.setItem('app_pin', pin); 
                
                // Sembunyikan login, tampilkan dashboard
                document.getElementById('login-view').classList.add('hidden');
                document.getElementById('dashboard-view').classList.remove('hidden');
                document.getElementById('dashboard-view').classList.add('flex');
            } else {
                document.getElementById('login-error').classList.remove('hidden');
            }
        }

        function handleLogout() {
            sessionStorage.removeItem('app_pin');
            document.getElementById('pin-input').value = '';
            document.getElementById('login-view').classList.remove('hidden');
            document.getElementById('dashboard-view').classList.add('hidden');
            document.getElementById('dashboard-view').classList.remove('flex');
        }
    </script>
</body>
</html>
