import bpy
import os

class FBXExportPreparation:
    """
    为 FBX 导出准备场景的完整解决方案
    包括材质转换、纹理烘焙和粒子系统处理
    """
    
    def __init__(self):
        def __init__(self):
            self.report = {
                'materials_converted': 0,
                'materials_baked': 0,
                'particles_converted': 0,
                'objects_processed': 0
            }
            self.skip_baking = False  # 新增：跳过烘焙标志
            
    def prepare_scene_for_fbx_export(self, bake_textures=True, convert_particles=True, cleanup=False):
        """
        主函数：准备整个场景用于 FBX 导出
        cleanup: 是否清理未使用的数据（默认False，避免崩溃）
        """
        print("=" * 60)
        print("开始准备场景用于 FBX 导出...")
        print("=" * 60)
        
        # 检查是否已经烘焙过
        blend_file_path = bpy.data.filepath
        if blend_file_path:
            bake_dir = os.path.join(os.path.dirname(blend_file_path), "baked_textures")
            if os.path.exists(bake_dir):
                baked_files = [f for f in os.listdir(bake_dir) if f.endswith('.png')]
                if len(baked_files) > 50:  # 如果已经有很多烘焙纹理
                    print(f"\n发现 {len(baked_files)} 个已烘焙的纹理文件")
                    print("跳过烘焙步骤，直接使用现有纹理...")
                    self.skip_baking = True
                    bake_textures = False
        
        # 1. 分析场景
        self.analyze_scene()
        
        # 2. 转换所有材质为 Principled BSDF
        self.convert_all_materials_to_principled()
        
        # 3. 烘焙纹理（如果需要且未跳过）
        if bake_textures and not self.skip_baking:
            self.bake_all_materials()
        elif self.skip_baking:
            # 使用已有的烘焙纹理
            self.apply_existing_baked_textures()
        
        # 4. 处理粒子系统
        if convert_particles:
            self.convert_particles_to_mesh()
        
        # 5. 清理场景（可选，默认关闭）
        if cleanup:
            print("\n[5/6] 清理场景...")
            print("  ⚠ 警告：清理功能可能导致崩溃，已跳过")
            print("  提示：可以在导出 FBX 后手动清理")
        
        # 6. 打印报告
        self.print_report()
        
        print("\n场景准备完成！现在可以导出 FBX 了。")
        return True
            

    def apply_existing_baked_textures(self):
        """
        应用已存在的烘焙纹理
        """
        print("\n[3/6] 应用已有的烘焙纹理...")
        
        blend_file_path = bpy.data.filepath
        if not blend_file_path:
            print("  ⚠ 警告: 文件未保存")
            return
        
        bake_dir = os.path.join(os.path.dirname(blend_file_path), "baked_textures")
        if not os.path.exists(bake_dir):
            print("  未找到烘焙纹理目录")
            return
        
        # 遍历所有材质
        for material in bpy.data.materials:
            if not material.use_nodes:
                continue
            
            nodes = material.node_tree.nodes
            
            # 查找是否已有图像纹理节点
            has_baked_texture = False
            for node in nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    if 'baked' in node.image.name.lower():
                        has_baked_texture = True
                        print(f"  ✓ {material.name} 已应用烘焙纹理")
                        self.report['materials_baked'] += 1
                        break
            
            if not has_baked_texture:
                # 尝试加载对应的烘焙纹理
                for filename in os.listdir(bake_dir):
                    if material.name in filename and filename.endswith('.png'):
                        image_path = os.path.join(bake_dir, filename)
                        
                        # 加载或获取图像
                        if filename in bpy.data.images:
                            baked_image = bpy.data.images[filename]
                        else:
                            baked_image = bpy.data.images.load(image_path)
                        
                        # 简化材质
                        self.simplify_material_with_baked_texture(material, baked_image)
                        print(f"  ✓ 应用烘焙纹理: {material.name}")
                        self.report['materials_baked'] += 1
                        break
    def analyze_scene(self):
        """
        分析场景中的材质和对象
        """
        print("\n[1/6] 分析场景...")
        
        shader_types = {}
        particle_objects = []
        
        for obj in bpy.context.view_layer.objects:
            # 检查粒子系统
            if obj.particle_systems:
                particle_objects.append(obj)
            
            # 检查材质
            if obj.type == 'MESH' and obj.material_slots:
                for slot in obj.material_slots:
                    if slot.material and slot.material.use_nodes:
                        shader_type = self.identify_shader_type(slot.material)
                        shader_types[shader_type] = shader_types.get(shader_type, 0) + 1
        
        print(f"\n材质类型统计:")
        for shader, count in shader_types.items():
            print(f"  - {shader}: {count} 个")
        
        if particle_objects:
            print(f"\n发现 {len(particle_objects)} 个带粒子系统的对象:")
            for obj in particle_objects:
                print(f"  - {obj.name} ({len(obj.particle_systems)} 个粒子系统)")
    
    def identify_shader_type(self, material):
        """
        识别材质的着色器类型
        """
        if not material.use_nodes:
            return "传统材质"
        
        nodes = material.node_tree.nodes
        
        # 查找主要着色器节点
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return "Principled BSDF (已优化)"
            elif node.type == 'GROUP':
                if 'mmd' in node.name.lower():
                    return "MMD Shader"
                else:
                    return f"节点组: {node.name}"
            elif node.type in ['BSDF_DIFFUSE', 'BSDF_GLOSSY', 'EMISSION']:
                return f"{node.type}"
        
        return "未知着色器"
    
    def convert_all_materials_to_principled(self):
        """
        将所有材质转换为 Principled BSDF
        """
        print("\n[2/6] 转换材质为 Principled BSDF...")
        
        for material in bpy.data.materials:
            if not material.use_nodes:
                material.use_nodes = True
            
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            
            # 检查是否已经有 Principled BSDF
            has_principled = any(node.type == 'BSDF_PRINCIPLED' for node in nodes)
            
            if has_principled:
                print(f"  ✓ {material.name} 已经是 Principled BSDF")
                continue
            
            # 查找输出节点
            output_node = None
            for node in nodes:
                if node.type == 'OUTPUT_MATERIAL':
                    output_node = node
                    break
            
            if not output_node:
                output_node = nodes.new('ShaderNodeOutputMaterial')
            
            # 创建新的 Principled BSDF
            principled = nodes.new('ShaderNodeBsdfPrincipled')
            principled.location = (output_node.location.x - 300, output_node.location.y)
            
            # 尝试提取现有纹理和颜色信息
            self.extract_texture_info(material, principled, nodes, links)
            
            # 连接到输出
            links.new(principled.outputs['BSDF'], output_node.inputs['Surface'])
            
            print(f"  ✓ 转换: {material.name}")
            self.report['materials_converted'] += 1
    
    def extract_texture_info(self, material, principled, nodes, links):
        """
        从现有材质中提取纹理信息
        """
        # 查找所有图像纹理节点
        image_nodes = [node for node in nodes if node.type == 'TEX_IMAGE']
        
        if not image_nodes:
            # 没有纹理，尝试提取颜色
            self.extract_color_from_nodes(nodes, principled)
            return
        
        # 按节点位置排序，通常第一个是主纹理
        image_nodes.sort(key=lambda n: n.location.x)
        
        # 连接主纹理到 Base Color
        main_texture = image_nodes[0]
        links.new(main_texture.outputs['Color'], principled.inputs['Base Color'])
        
        # 如果有 Alpha 通道，也连接上
        if main_texture.image and main_texture.image.channels == 4:
            links.new(main_texture.outputs['Alpha'], principled.inputs['Alpha'])
            material.blend_method = 'BLEND'
    
    def extract_color_from_nodes(self, nodes, principled):
        """
        从节点中提取颜色信息（修复版本）
        """
        try:
            for node in nodes:
                if not hasattr(node, 'inputs'):
                    continue
                
                for input_socket in node.inputs:
                    # 检查是否是颜色输入
                    if 'color' in input_socket.name.lower() or 'diffuse' in input_socket.name.lower():
                        if hasattr(input_socket, 'default_value'):
                            value = input_socket.default_value
                            
                            # 确保是有效的颜色值（RGBA 元组）
                            if isinstance(value, (tuple, list)) and len(value) >= 3:
                                # 确保有 4 个值（RGBA）
                                if len(value) == 3:
                                    color = (value[0], value[1], value[2], 1.0)
                                else:
                                    color = tuple(value[:4])
                                
                                principled.inputs['Base Color'].default_value = color
                                print(f"    提取到颜色: {color}")
                                return
                            elif isinstance(value, (int, float)):
                                # 单个值，转换为灰度
                                color = (value, value, value, 1.0)
                                principled.inputs['Base Color'].default_value = color
                                print(f"    提取到灰度: {value}")
                                return
        except Exception as e:
            print(f"    警告: 提取颜色时出错 - {str(e)}")
            # 使用默认白色
            principled.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
    
    def bake_all_materials(self):
        """
        烘焙所有材质到简单纹理
        """
        print("\n[3/6] 烘焙材质纹理...")
        
        # 创建烘焙输出目录
        blend_file_path = bpy.data.filepath
        if not blend_file_path:
            print("  ⚠ 警告: 文件未保存，跳过烘焙")
            print("  提示: 请先保存 Blender 文件，然后重新运行脚本")
            return
        
        bake_dir = os.path.join(os.path.dirname(blend_file_path), "baked_textures")
        if not os.path.exists(bake_dir):
            os.makedirs(bake_dir)
            print(f"  创建烘焙目录: {bake_dir}")
        
        # 设置烘焙参数
        original_engine = bpy.context.scene.render.engine
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.samples = 16  # 低采样，快速烘焙
        
        original_selection = list(bpy.context.selected_objects)
        original_active = bpy.context.view_layer.objects.active
        
        for obj in bpy.context.view_layer.objects:
            if obj.type != 'MESH' or not obj.material_slots:
                continue
            
            print(f"\n  处理对象: {obj.name}")
            
            # 选择并激活对象
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            
            for idx, slot in enumerate(obj.material_slots):
                if not slot.material:
                    continue
                
                material = slot.material
                
                # 为每个材质创建烘焙图像
                image_name = f"{obj.name}_{material.name}_baked".replace(" ", "_")
                
                # 检查图像是否已存在
                if image_name in bpy.data.images:
                    bake_image = bpy.data.images[image_name]
                else:
                    bake_image = bpy.data.images.new(
                        image_name,
                        width=2048,
                        height=2048,
                        alpha=True
                    )
                
                # 在材质中添加图像纹理节点用于烘焙
                if not material.use_nodes:
                    material.use_nodes = True
                
                nodes = material.node_tree.nodes
                
                # 查找或创建烘焙节点
                bake_node = None
                for node in nodes:
                    if node.type == 'TEX_IMAGE' and node.image == bake_image:
                        bake_node = node
                        break
                
                if not bake_node:
                    bake_node = nodes.new('ShaderNodeTexImage')
                    bake_node.location = (0, -300)
                
                bake_node.image = bake_image
                bake_node.select = True
                nodes.active = bake_node
                
                try:
                    # 执行烘焙
                    bpy.ops.object.bake(type='COMBINED', use_clear=True)
                    
                    # 保存烘焙的图像
                    bake_image.filepath_raw = os.path.join(bake_dir, f"{image_name}.png")
                    bake_image.file_format = 'PNG'
                    bake_image.save()
                    
                    print(f"    ✓ 烘焙材质: {material.name}")
                    self.report['materials_baked'] += 1
                    
                    # 简化材质为单一纹理
                    self.simplify_material_with_baked_texture(material, bake_image)
                    
                except Exception as e:
                    print(f"    ✗ 烘焙失败: {material.name} - {str(e)}")
        
        # 恢复原始设置
        bpy.context.scene.render.engine = original_engine
        
        # 恢复选择
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = original_active
    
    def simplify_material_with_baked_texture(self, material, baked_image):
        """
        用烘焙的纹理简化材质
        """
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # 清除所有节点
        nodes.clear()
        
        # 创建简单的材质设置
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (300, 0)
        
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)
        
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = baked_image
        tex_node.location = (-300, 0)
        
        # 连接节点
        links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
        links.new(tex_node.outputs['Alpha'], principled.inputs['Alpha'])
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    
    def convert_particles_to_mesh(self):
        """
        将粒子系统转换为网格对象
        """
        print("\n[4/6] 处理粒子系统...")
        
        particle_objects = [obj for obj in bpy.data.objects if obj.particle_systems]
        
        if not particle_objects:
            print("  未发现粒子系统")
            return
        
        for obj in particle_objects:
            print(f"\n  处理对象: {obj.name}")
            
            # 保存原始选择
            original_selection = list(bpy.context.selected_objects)
            
            for ps_idx in range(len(obj.particle_systems) - 1, -1, -1):
                ps = obj.particle_systems[ps_idx]
                print(f"    粒子系统: {ps.name}")
                
                # 选择对象
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                
                # 设置粒子系统为活动
                obj.particle_systems.active_index = ps_idx
                
                try:
                    # 转换为真实对象
                    bpy.ops.object.duplicates_make_real()
                    
                    # 获取转换后的对象
                    converted_objects = [o for o in bpy.context.selected_objects if o != obj]
                    
                    if converted_objects:
                        # 合并所有转换的对象
                        bpy.context.view_layer.objects.active = converted_objects[0]
                        
                        if len(converted_objects) > 1:
                            bpy.ops.object.join()
                        
                        converted_mesh = bpy.context.active_object
                        converted_mesh.name = f"{obj.name}_particles_{ps.name}"
                        
                        print(f"    ✓ 转换为网格: {converted_mesh.name} ({len(converted_objects)} 个实例)")
                        self.report['particles_converted'] += 1
                    else:
                        print(f"    ⚠ 警告: 粒子系统 {ps.name} 未生成任何对象")
                    
                except Exception as e:
                    print(f"    ✗ 转换失败: {str(e)}")
            
            # 移除原始对象的所有粒子系统
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            
            while obj.particle_systems:
                obj.particle_systems.active_index = 0
                bpy.ops.object.particle_system_remove()
            
            print(f"    ✓ 已移除 {obj.name} 的所有粒子系统")
    
    def cleanup_scene(self):
        """
        清理场景，移除不必要的数据
        """
        # print("\n[5/6] 清理场景...")
        pass
        
        # # 移除未使用的数据块
        # for i in range(3):  # 多次清理以确保彻底
        #     bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        
        print("  ✓ 已清理未使用的数据")
    
    def print_report(self):
        """
        打印处理报告
        """
        print("\n" + "=" * 60)
        print("处理报告:")
        print("=" * 60)
        print(f"转换的材质数: {self.report['materials_converted']}")
        print(f"烘焙的材质数: {self.report['materials_baked']}")
        print(f"转换的粒子系统: {self.report['particles_converted']}")
        print("=" * 60)

def export_fbx_with_settings(filepath):
    """
    使用优化的设置导出 FBX
    """
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=False,
        
        # 嵌入设置
        embed_textures=True,
        path_mode='COPY',
        
        # 网格设置
        use_mesh_modifiers=True,
        mesh_smooth_type='FACE',
        
        # 材质设置
        use_custom_props=True,
        
        # 坐标轴设置（Unity）
        axis_forward='-Z',
        axis_up='Y',
        
        # 缩放
        global_scale=1.0,
        apply_scale_options='FBX_SCALE_ALL',
        
        # 其他
        bake_anim=False,
    )
    print(f"\n✓ FBX 已导出到: {filepath}")

# ============ 使用示例 ============

if __name__ == "__main__":
    # 创建处理器实例
    processor = FBXExportPreparation()
    
    # 准备场景
    # cleanup=False: 不清理资产（避免崩溃）
    processor.prepare_scene_for_fbx_export(
        bake_textures=True,      # 会自动检测已有纹理
        convert_particles=True,
        cleanup=False            # 关闭清理功能
    )
    
    # 导出 FBX
    print("\n准备导出 FBX...")
    blend_file = bpy.data.filepath
    if blend_file:
        fbx_path = blend_file.replace('.blend', '_export.fbx')
        export_fbx_with_settings(fbx_path)
    else:
        print("⚠ 警告: 请先保存文件，然后手动导出 FBX")
        print("File > Export > FBX (.fbx)")